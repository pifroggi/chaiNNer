# type: ignore
# Original Rife Frame Interpolation by hzwer
# https://github.com/megvii-research/ECCV2022-RIFE
# https://github.com/hzwer/Practical-RIFE

# Modifications to use Rife for Image Alignment by tepete/pifroggi ('Enhance Everything!' Discord Server)

# Additional helpful github issues
# https://github.com/megvii-research/ECCV2022-RIFE/issues/278
# https://github.com/megvii-research/ECCV2022-RIFE/issues/344

import torch
import torch.nn.functional as F  # noqa: N812
from torch import nn
from torchvision import transforms

from .warplayer import warp


def conv(in_planes, out_planes, kernel_size=3, stride=1, padding=1, dilation=1):  # noqa: ANN001
    return nn.Sequential(
        nn.Conv2d(
            in_planes,
            out_planes,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            dilation=dilation,
            bias=True,
        ),
        nn.LeakyReLU(0.2, True),
    )


def conv_bn(in_planes, out_planes, kernel_size=3, stride=1, padding=1, dilation=1):  # noqa: ANN001
    return nn.Sequential(
        nn.Conv2d(
            in_planes,
            out_planes,
            kernel_size=kernel_size,
            stride=stride,
            padding=padding,
            dilation=dilation,
            bias=False,
        ),
        nn.BatchNorm2d(out_planes),
        nn.LeakyReLU(0.2, True),
    )


class Head(nn.Module):
    def __init__(self):
        super().__init__()
        self.cnn0 = nn.Conv2d(3, 32, 3, 2, 1)
        self.cnn1 = nn.Conv2d(32, 32, 3, 1, 1)
        self.cnn2 = nn.Conv2d(32, 32, 3, 1, 1)
        self.cnn3 = nn.ConvTranspose2d(32, 8, 4, 2, 1)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x, feat=False):  # noqa: ANN001
        x0 = self.cnn0(x)
        x = self.relu(x0)
        x1 = self.cnn1(x)
        x = self.relu(x1)
        x2 = self.cnn2(x)
        x = self.relu(x2)
        x3 = self.cnn3(x)
        if feat:
            return [x0, x1, x2, x3]
        return x3


class ResConv(nn.Module):
    def __init__(self, c, dilation=1):  # noqa: ANN001
        super().__init__()
        self.conv = nn.Conv2d(c, c, 3, 1, dilation, dilation=dilation, groups=1)
        self.beta = nn.Parameter(torch.ones((1, c, 1, 1)), requires_grad=True)
        self.relu = nn.LeakyReLU(0.2, True)

    def forward(self, x):  # noqa: ANN001
        return self.relu(self.conv(x) * self.beta + x)


class IFBlock(nn.Module):
    def __init__(self, in_planes, c=64):  # noqa: ANN001
        super().__init__()
        self.conv0 = nn.Sequential(
            conv(in_planes, c // 2, 3, 2, 1),
            conv(c // 2, c, 3, 2, 1),
        )
        self.convblock = nn.Sequential(
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
            ResConv(c),
        )
        self.lastconv = nn.Sequential(
            nn.ConvTranspose2d(c, 4 * 6, 4, 2, 1), nn.PixelShuffle(2)
        )

    def forward(self, x, flow=None, scale=1):  # noqa: ANN001
        x = F.interpolate(
            x, scale_factor=1.0 / scale, mode="bilinear", align_corners=False
        )
        if flow is not None:
            flow = (
                F.interpolate(
                    flow, scale_factor=1.0 / scale, mode="bilinear", align_corners=False
                )
                * 1.0
                / scale
            )
            x = torch.cat((x, flow), 1)
        feat = self.conv0(x)
        feat = self.convblock(feat)
        tmp = self.lastconv(feat)
        tmp = F.interpolate(
            tmp, scale_factor=scale, mode="bilinear", align_corners=False
        )
        flow = tmp[:, :4] * scale
        mask = tmp[:, 4:5]
        return flow, mask


class IFNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.block0 = IFBlock(7 + 16, c=192)
        self.block1 = IFBlock(8 + 4 + 16, c=128)
        self.block2 = IFBlock(8 + 4 + 16, c=96)
        self.block3 = IFBlock(8 + 4 + 16, c=64)
        self.encode = Head()

    def align_images(
        self,
        img0,  # noqa: ANN001
        img1,  # noqa: ANN001
        timestep,  # noqa: ANN001
        scale_list,  # noqa: ANN001
        blur_strength,  # noqa: ANN001
        ensemble,  # noqa: ANN001
        device,  # noqa: ANN001
        flow2=None,  # noqa: ANN001
        img1_blurred=None,  # noqa: ANN001
    ):
        def compute_flow(
            img0_blurred: np.ndarray, img1_blurred: np.ndarray, timestep: float
        ) -> None:
            f0 = self.encode(img0_blurred[:, :3])
            f1 = self.encode(img1_blurred[:, :3])
            flow = None
            mask = None
            block = [self.block0, self.block1, self.block2, self.block3]
            for i in range(4):
                if flow is None:
                    flow, mask = block[i](
                        torch.cat(
                            (
                                img0_blurred[:, :3],
                                img1_blurred[:, :3],
                                f0,
                                f1,
                                timestep,
                            ),
                            1,
                        ),
                        None,
                        scale=scale_list[i],
                    )
                    if ensemble:
                        f_, m_ = block[i](
                            torch.cat(
                                (
                                    img1_blurred[:, :3],
                                    img0_blurred[:, :3],
                                    f1,
                                    f0,
                                    1 - timestep,
                                ),
                                1,
                            ),
                            None,
                            scale=scale_list[i],
                        )
                        flow = (flow + torch.cat((f_[:, 2:4], f_[:, :2]), 1)) / 2
                        mask = (mask + (-m_)) / 2
                else:
                    wf0 = warp(f0, flow[:, :2], device)
                    wf1 = warp(f1, flow[:, 2:4], device)
                    fd, m0 = block[i](
                        torch.cat(
                            (
                                img0_blurred[:, :3],
                                img1_blurred[:, :3],
                                wf0,
                                wf1,
                                timestep,
                                mask,
                            ),
                            1,
                        ),
                        flow,
                        scale=scale_list[i],
                    )
                    if ensemble:
                        f_, m_ = block[i](
                            torch.cat(
                                (
                                    img1_blurred[:, :3],
                                    img0_blurred[:, :3],
                                    wf1,
                                    wf0,
                                    1 - timestep,
                                    -mask,
                                ),
                                1,
                            ),
                            torch.cat((flow[:, 2:4], flow[:, :2]), 1),
                            scale=scale_list[i],
                        )
                        fd = (fd + torch.cat((f_[:, 2:4], f_[:, :2]), 1)) / 2
                        mask = (m0 + (-m_)) / 2
                    else:
                        mask = m0
                    flow = flow + fd
            return flow

        # Optional blur
        if blur_strength is not None and blur_strength > 0:
            blur = transforms.GaussianBlur(
                kernel_size=(5, 5), sigma=(blur_strength, blur_strength)
            )
            img0_blurred = blur(img0)
            if img1_blurred is None:
                img1_blurred = blur(img1)
        else:
            img0_blurred = img0
            img1_blurred = img1

        # align image to reference
        flow1 = compute_flow(img0_blurred, img1_blurred, timestep)

        # align image to itself
        if flow2 is None:
            flow2 = compute_flow(img1_blurred, img1_blurred, timestep)

        # subtract flow2 from flow1 to compensate for shifts
        compensated_flow = flow1 - flow2

        # warp image with the compensated flow
        aligned_img0 = warp(img0, compensated_flow[:, :2], device)

        # add clamp here instead of in warplayer script, as it changes the output there
        aligned_img0 = aligned_img0.clamp(0, 1)
        return aligned_img0, compensated_flow, flow2, img1_blurred

    def forward(
        self,
        x,  # noqa: ANN001
        timestep=1,  # noqa: ANN001
        training=False,  # noqa: ANN001
        fastmode=True,  # noqa: ANN001
        ensemble=True,  # noqa: ANN001
        num_iterations=1,  # noqa: ANN001
        multiplier=0.5,  # noqa: ANN001
        blur_strength=0,  # noqa: ANN001
        device="cuda",  # noqa: ANN001
    ):
        if not training:
            channel = x.shape[1] // 2
            img0 = x[:, :channel]
            img1 = x[:, channel:]

        scale_list = [multiplier * 8, multiplier * 4, multiplier * 2, multiplier]

        if not torch.is_tensor(timestep):
            timestep = (x[:, :1].clone() * 0 + 1) * timestep
        else:
            timestep = timestep.repeat(1, 1, img0.shape[2], img0.shape[3])  # type: ignore

        flow2 = None
        img1_blurred = None
        for _iteration in range(num_iterations):
            aligned_img0, flow, flow2, img1_blurred = self.align_images(
                img0,
                img1,
                timestep,
                scale_list,
                blur_strength,
                ensemble,
                device,
                flow2,
                img1_blurred,
            )
            img0 = aligned_img0  # use the aligned image as img0 for the next iteration

        return aligned_img0, flow
