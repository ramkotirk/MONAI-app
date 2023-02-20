import torch
import torch.nn as nn
import torch.nn.functional as F

from monai.networks.blocks.convolutions import Convolution
from monai.networks.blocks.backbone_fpn_utils import DAF3D_BackboneWithFPN
from monai.networks.blocks.aspp import DAF3D_ASPP
from monai.networks.nets.resnet import DAF3D_ResNet, DAF3D_ResNetBottleneck


class AttentionModule(nn.Module):
    def __init__(self):
        super().__init__()

        group_norm = ("group", {"num_groups": 32, "num_channels" : 64})
        
        self.attentive_map = nn.Sequential(
            Convolution(spatial_dims=3, in_channels=192, out_channels=64, kernel_size=1, norm=group_norm, act="PRELU"),
            Convolution(spatial_dims=3, in_channels=64, out_channels=64, kernel_size=3, padding=1, norm=group_norm, act="PRELU"),
            Convolution(spatial_dims=3, in_channels=64, out_channels=64, kernel_size=3, padding=1, adn_ordering="A", act="SIGMOID")
        )
        self.refine = nn.Sequential(
            Convolution(spatial_dims=3, in_channels=192, out_channels=64, kernel_size=1, norm=group_norm, act="PRELU"),
            Convolution(spatial_dims=3, in_channels=64, out_channels=64, kernel_size=3, padding=1, norm=group_norm, act="PRELU"),
            Convolution(spatial_dims=3, in_channels=64, out_channels=64, kernel_size=3, padding=1, norm=group_norm, act="PRELU"),
        )

    def forward(self, slf, mlf):
        att = self.attentive_map(torch.cat((slf, mlf), 1))
        out = self.refine(torch.cat((slf, att * mlf), 1))
        return out

class DAF3D_Backbone(nn.Module):
    def __init__(self):
        super().__init__()
        net = DAF3D_ResNet(DAF3D_ResNetBottleneck, [3,4,6,3], [128,256,512,1024])
        net = list(net.children())
        self.layer0 = nn.Sequential(*net[:3])
        # the layer0 contains the first convolution, bn and relu
        self.layer1 = nn.Sequential(*net[3:5])
        # the layer1 contains the first pooling and the first 3 bottle blocks
        self.layer2 = net[5]
        # the layer2 contains the second 4 bottle blocks
        self.layer3 = net[6]
        # the layer3 contains the media bottle blocks
        # with 6 in 50-layers and 23 in 101-layers
        self.layer4 = net[7]
        # the layer4 contains the final 3 bottle blocks
        # according the backbone the next is avg-pooling and dense with num classes uints
        # but we don't use the final two layers in backbone networks
    
    def forward(self, x):
        layer0 = self.layer0(x)
        layer1 = self.layer1(layer0)
        layer2 = self.layer2(layer1)
        layer3 = self.layer3(layer2)
        layer4 = self.layer4(layer3)
        return layer4


class DAF3D_Monai(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone_with_fpn = DAF3D_BackboneWithFPN(backbone=DAF3D_Backbone(), return_layers={"layer1" : "feat1", "layer2" : "feat2", "layer3" : "feat3", "layer4" : "feat4"}, in_channels_list=[256, 512, 1024, 2048], out_channels=128, spatial_dims=3)
        self.predict1 = nn.Conv3d(128, 1, kernel_size=1)

        group_norm = ("group", {"num_groups": 32, "num_channels" : 64})
        act_prelu = ("prelu", {"num_parameters": 1, "init" : 0.25})
        self.fuse = nn.Sequential(
            Convolution(spatial_dims=3, in_channels=512, out_channels=64, kernel_size=1, adn_ordering="NA", norm=group_norm, act=act_prelu),
            Convolution(spatial_dims=3, in_channels=64, out_channels=64, kernel_size=3, adn_ordering="NA", padding=1, norm=group_norm, act=act_prelu),
            Convolution(spatial_dims=3, in_channels=64, out_channels=64, kernel_size=3, adn_ordering="NA", padding=1, norm=group_norm, act=act_prelu)
        )
        self.attention = AttentionModule()

        self.refine = Convolution(3, 256, 64, kernel_size=1, adn_ordering="NA", norm=group_norm, act=act_prelu)
        self.predict2 = nn.Conv3d(64, 1, kernel_size=1)
        self.aspp = DAF3D_ASPP(3, 64, 64, kernel_sizes=(3,3,3,3), dilations=((1,1,1), (1,6,6), (1,12,12), (1,18,18)), norm_type=group_norm, bias=True)


    def forward(self, x):
        #layers from 1 - 4
        single_layer_features = [l for l in self.backbone_with_fpn(x).values()]
        #first 4 supervised signals (slfs 1 - 4) 
        supervised1 = [self.predict1(slf) for slf in single_layer_features]
        mlf = self.fuse(torch.cat(single_layer_features, 1))
        attentive_feature_maps = [self.attention(slf, mlf) for slf in single_layer_features]
        #second 4 supervised signals (af 1 - 4)
        supervised2 = [self.predict2(af) for af in attentive_feature_maps]
        attentive_mlf = self.refine(torch.cat(attentive_feature_maps, 1))
        aspp = self.aspp(attentive_mlf)
        supervised_final = self.predict2(aspp)

        if self.training:
            output = supervised1 + supervised2 + [supervised_final]
            output = [F.interpolate(o, size=x.size()[2:], mode='trilinear') for o in output]
        else:
            output = F.interpolate(supervised_final, size=x.size()[2:], mode='trilinear') 
        return output