from moviepy.editor import VideoFileClip
from PIL import Image
import numpy as np
import sys

src = 'build/output_short_ffmpeg_final.mp4'
out = 'build/frame0.png'
try:
    clip = VideoFileClip(src)
except Exception as e:
    print('ERROR opening video:', e)
    sys.exit(2)

frame = clip.get_frame(0.5 if clip.duration>0.5 else 0)
img = Image.fromarray(frame)
img.save(out)
print('Wrote frame to', out)
arr = np.array(img)
# downsample sample grid
sample = arr[::20, ::20]
# count unique RGB tuples
unique = set(tuple(pixel) for row in sample for pixel in row)
print('unique_colors_sample:', len(unique))
print('mean_rgb:', sample.mean(axis=(0,1)).tolist())
# compute alpha presence if exists
if arr.shape[2]==4:
    print('alpha stats: min,max,mean', arr[:,:,3].min(), arr[:,:,3].max(), arr[:,:,3].mean())
