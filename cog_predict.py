# flake8: noqa
# This file is used for deploying replicate models
# running: cog predict -i img=@inputs/whole_imgs/10045.png -i version='v1.4' -i scale=2
# push: cog push r8.im/xinntao/realesrgan

import os

os.system('pip install gfpgan')
os.system('python setup.py develop')

import cv2
import shutil
import tempfile
import torch
from basicsr.archs.rrdbnet_arch import RRDBNet
from basicsr.archs.srvgg_arch import SRVGGNetCompact

from realesrgan.utils import RealESRGANer

try:
    from cog import BasePredictor, Input, Path
    from gfpgan import GFPGANer
except Exception:
    print('please install cog and realesrgan package')


class Predictor(BasePredictor):

    def setup(self):
        # download weights
        if not os.path.exists('realesrgan/weights/realesr-general-x4v3.pth'):
            os.system(
                'wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth -P ./realesrgan/weights'
            )
        if not os.path.exists('realesrgan/weights/GFPGANv1.4.pth'):
            os.system(
                'wget https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth -P ./realesrgan/weights'
            )
        if not os.path.exists('realesrgan/weights/RealESRGAN_x4plus.pth'):
            os.system(
                'wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth -P ./realesrgan/weights'
            )
        if not os.path.exists('realesrgan/weights/RealESRGAN_x4plus_anime_6B.pth'):
            os.system(
                'wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth -P ./realesrgan/weights'
            )
        if not os.path.exists('realesrgan/weights/realesr-animevideov3.pth'):
            os.system(
                'wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-animevideov3.pth -P ./realesrgan/weights'
            )

    def choose_model(self, scale, version, tile=0):
        half = True if torch.cuda.is_available() else False
        if version == 'General - RealESRGANplus':
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
            model_path = 'realesrgan/weights/RealESRGAN_x4plus.pth'
            self.upsampler = RealESRGANer(
                scale=4, model_path=model_path, model=model, tile=tile, tile_pad=10, pre_pad=0, half=half)
        elif version == 'General - v3':
            model = SRVGGNetCompact(num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=32, upscale=4, act_type='prelu')
            model_path = 'realesrgan/weights/realesr-general-x4v3.pth'
            self.upsampler = RealESRGANer(
                scale=4, model_path=model_path, model=model, tile=tile, tile_pad=10, pre_pad=0, half=half)
        elif version == 'Anime - anime6B':
            model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=6, num_grow_ch=32, scale=4)
            model_path = 'realesrgan/weights/RealESRGAN_x4plus_anime_6B.pth'
            self.upsampler = RealESRGANer(
                scale=4, model_path=model_path, model=model, tile=tile, tile_pad=10, pre_pad=0, half=half)
        elif version == 'AnimeVideo - v3':
            model = SRVGGNetCompact(num_in_ch=3, num_out_ch=3, num_feat=64, num_conv=16, upscale=4, act_type='prelu')
            model_path = 'realesrgan/weights/realesr-animevideov3.pth'
            self.upsampler = RealESRGANer(
                scale=4, model_path=model_path, model=model, tile=tile, tile_pad=10, pre_pad=0, half=half)

        self.face_enhancer = GFPGANer(
            model_path='realesrgan/weights/GFPGANv1.4.pth',
            upscale=scale,
            arch='clean',
            channel_multiplier=2,
            bg_upsampler=self.upsampler)

    def predict(
        self,
        img: Path = Input(description='Input'),
        version: str = Input(
            description='RealESRGAN version. Please see [Readme] below for more descriptions',
            choices=['General - RealESRGANplus', 'General - v3', 'Anime - anime6B', 'AnimeVideo - v3'],
            default='General - v3'),
        scale: float = Input(description='Rescaling factor', default=2),
        face_enhance: bool = Input(
            description='Enhance faces with GFPGAN. Note that it does not work for anime images/vidoes.',
            default=False),
        tile: int = Input(
            description=
            'Tile size. When encountering out-of-GPU-memory issue, please decrease it (e.g., 400). 0 for no tile',
            default=0),
    ) -> Path:
        print(f'img: {img}. version: {version}. scale: {scale}. face_enhance: {face_enhance}. tile: {tile}.')
        try:
            img = cv2.imread(str(img), cv2.IMREAD_UNCHANGED)
            if len(img.shape) == 3 and img.shape[2] == 4:
                img_mode = 'RGBA'
            else:
                img_mode = None

            h, w = img.shape[0:2]
            if h < 300:
                img = cv2.resize(img, (w * 2, h * 2), interpolation=cv2.INTER_LANCZOS4)

            self.choose_model(scale, version, tile)

            try:
                if face_enhance:
                    _, _, output = self.face_enhancer.enhance(
                        img, has_aligned=False, only_center_face=False, paste_back=True)
                else:
                    output, _ = self.upsampler.enhance(img, outscale=scale)
            except RuntimeError as error:
                print('Error', error)
                print('If you encounter CUDA out of memory, try to set "tile" to a smaller size, e.g., 400.')
            else:
                extension = 'png'

            if img_mode == 'RGBA':  # RGBA images should be saved in png format
                extension = 'png'
            else:
                extension = 'jpg'
            save_path = f'output/out.{extension}'
            cv2.imwrite(save_path, output)
            out_path = Path(tempfile.mkdtemp()) / 'output.png'
            cv2.imwrite(str(out_path), output)
        except Exception as error:
            print('global exception', error)
        finally:
            clean_folder('output')
        return out_path


def clean_folder(folder):
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')
