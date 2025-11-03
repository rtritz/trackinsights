import requests
from bs4 import BeautifulSoup
import os

# Gallery URL
url = 'https://www.indystar.com/picture-gallery/sports/high-school/2025/06/07/see-photos-from-the-ihsaa-51st-annual-girls-track-and-field-state-finals/84096994007/'
url = 'https://www.indystar.com/picture-gallery/sports/high-school/2025/06/07/see-photos-from-the-ihsaa-121st-annual-boys-track-and-field-state-finals/84083697007/'

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
}

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.text, 'html.parser')

img_tags = soup.find_all('img')

downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads", "background_images_girls")
downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads", "background_images_boys")
os.makedirs(downloads_folder, exist_ok=True)

count = 1
for img in img_tags:
    src = img.get('src')
    # Only proceed if src exists, is relative, and clearly a photo (not tracker)
    if src and '/authoring-images/' in src:
        if src.startswith('/'):
            src = 'https://www.indystar.com' + src
        # Prefer to download the higher-res image from srcset if available
        srcset = img.get('srcset')
        if srcset:
            # srcset is comma-separated "url descriptor, url descriptor" e.g. ...660..1x, ...1320..2x
            parts = [s.strip() for s in srcset.split(',')]
            # usually the 2x variant is the last one
            hi_res = parts[-1].split()[0]
            if hi_res.startswith('/'):
                hi_res = 'https://www.indystar.com' + hi_res
            src = hi_res  # override src with the higher-res link

        try:
            img_data = requests.get(src, headers=headers).content
            filename = f'bg_{count}.jpg'
            file_path = os.path.join(downloads_folder, filename)
            with open(file_path, 'wb') as handler:
                handler.write(img_data)
            print(f'Downloaded {filename} from {src}')
            count += 1
        except Exception as e:
            print(f'Skipping {src}: {e}')
