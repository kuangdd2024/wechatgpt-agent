import pathlib
import tempfile
import time
import re
import os

import openai
import openai.error

from common.log import logger
from config import conf

import requests
from PIL import Image, ImageDraw, ImageFont

_root_dir = '/'.join(pathlib.Path(__file__).absolute().parts[:-3])


# Pollinations提供的画图接口
class NotebotImage(object):
    def __init__(self):
        pass

    def create_img(self, query, retry_count=0):
        try:
            logger.info("[Pollinations] image_query={}".format(query))

            m = re.match(r'(\d+)\s*[+\-x*/]\s*(\d+)(.+)', query)
            if m:
                w = m.group(1)
                h = m.group(2)
                query = m.group(3)
            else:
                size = conf().get("image_create_size", "768x768")
                w, h = size.split('x')
            image_url = f'https://image.pollinations.ai/prompt/{query}?width={w}&height={h}&seed={int(time.time())}&nologo=true&model=flux'
            try:
                response = requests.get(image_url, verify=False, timeout=(10, 20))
            except requests.exceptions.ConnectionError as e:
                print(dict(img_url=image_url, error=e))
                import traceback
                traceback.print_exc()
                response = None

            image_path = tempfile.TemporaryFile(prefix='chars-', suffix='.png').name
            if response and response.status_code == 200:
                img_data = response.content
                # open(image_path, 'wb').write(img_data)
                # image_url = image_path
            else:
                print(dict(response=response, img_url=image_url))
                text = re.sub(r'(\w+?\W+)', r'\1\n', query)
                img_path = self.create_char_image(text, image=f'{size}/73-109-137', font="msyh.ttc+40",
                                                  location=(0.5, 0.5),
                                                  color=(255, 255, 255), image_output=image_path)

                img_data = open(img_path, 'rb').read()
                image_url = img_path

            logger.info("[pollinations] image_url={}".format(image_url))
            return True, image_url
        except openai.error.RateLimitError as e:
            logger.warn(e)
            if retry_count < 1:
                time.sleep(5)
                logger.warn("[pollinations] ImgCreate RateLimit exceed, 第{}次重试".format(retry_count + 1))
                return self.create_img(query, retry_count + 1)
            else:
                return False, "画图出现问题，请休息一下再问我吧"
        except Exception as e:
            logger.exception(e)
            return False, "画图出现问题，请休息一下再问我吧"

    def create_chars_image(self, text, image="1280x720/73-109-137", font="msyh.ttc+40", location=(0.5, 0.85),
                           color=(255, 255, 255),
                           image_output=''):
        if re.match(r'\d+x\d+/\d+-\d+-\d+', image):
            size, desc = image.split('/')
            width, height = size.split('x')
            red, green, blue = desc.split('-')
            img_path = image

            img = Image.new('RGB', (int(width), int(height)), color=(int(red), int(green), int(blue)))
        else:
            img_path = image
            img = Image.open(img_path)

        d = ImageDraw.Draw(img)

        font_name, font_size = font.split('+')
        # 使用Windows系统中的微软雅黑字体
        font_path = f"C:/Windows/Fonts/{font_name}"  # 微软雅黑字体文件路径
        if not os.path.isfile(font_path):
            font_path = os.path.join(_root_dir, f'static/fonts/{font_name}')
        font_file = ImageFont.truetype(font_path, int(font_size))
        bbox = d.textbbox((0, 0), text, font=font_file)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        width, height = img.size
        x = (width - text_w) * location[0]
        y = (height - text_h) * location[1]
        d.text((x, y), text, font=font_file, fill=color)
        outpath = image_output or tempfile.TemporaryFile(prefix='chars-', suffix='.png').name
        img.save(outpath)
        return outpath
