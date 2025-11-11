import numpy as np
import time
import subprocess
import os
import ntpath
import sys

import cv2 as cv

from SettingsLoader import loadSettings
from Exceptions import *
from Weights import *

def blend(imgs, weights):
    try:
        img = np.einsum("ijkl,i->jkl", imgs, weights)
        return img.astype(np.uint8)
    except ValueError:
        img = np.zeros(imgs.shape)
        return img

# To fix weird OpenCV colorspace, code by caffeine
def colourFix(input_name):
    filename = ntpath.basename(input_name)
    os.rename(f"{input_name}", f"to-fix_{filename}")
    command = f'ffmpeg -i "to-fix_{input_name}" -vcodec libx264 -preset ultrafast -crf 1 -vf colormatrix=bt601:bt709,eq=gamma_g=0.97 -c:a copy "{input_name}"'
    subprocess.call(command, shell=True)

def addAudio(input_name, output_name):
    command = f'ffmpeg -i "no-audio_{output_name}" -i "{input_name}" -map 0:v -map 1:a -c copy "{output_name}"'
    subprocess.call(command, shell=True)
    os.remove(f"no-audio_{output_name}")

# overengineered resolution string parsing
def parseResolution(in_res, out_res):
    if out_res == "UNCHANGED":
        return in_res

    try:
        res = out_res.split("x")
    except:
        raise InvalidResolution()

    new_res = []
    for value in res:
        try:
            new_res.append(int(value))
        except ValueError:
            raise InvalidResolution()

    if(len(new_res) != 2):
        raise InvalidResolution()
    else:
        return new_res

def buildEncoderCommand(encoder_settings, output_res, output_fps, output_name):
    """Build FFmpeg command based on encoder settings"""
    encoder = encoder_settings.get("encoder", "libx264")
    preset = encoder_settings.get("preset", "medium")
    crf = encoder_settings.get("crf", 18)
    pixel_format = encoder_settings.get("pixel_format", "yuv420p")
    extra_params = encoder_settings.get("extra_params", [])
    
    cmd = [
        'ffmpeg',
        '-y',  # Overwrite output
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-s', f'{output_res[0]}x{output_res[1]}',
        '-pix_fmt', 'bgr24',
        '-r', str(output_fps),
        '-i', '-',  # Input from pipe
        '-c:v', encoder,
    ]
    
    # Add preset if supported by encoder
    if encoder in ['libx264', 'libx265', 'h264_nvenc', 'hevc_nvenc', 'h264_qsv', 'hevc_qsv']:
        cmd.extend(['-preset', preset])
    
    # Add CRF/quality settings based on encoder
    if encoder in ['libx264', 'libx265']:
        cmd.extend(['-crf', str(crf)])
    elif encoder in ['h264_nvenc', 'hevc_nvenc']:
        cmd.extend(['-cq', str(crf)])  # NVENC uses -cq instead of -crf
    elif encoder in ['h264_qsv', 'hevc_qsv']:
        cmd.extend(['-global_quality', str(crf)])  # QSV uses global_quality
    elif encoder == 'h264_amf':
        cmd.extend(['-quality', 'quality', '-qp_i', str(crf)])
    
    # Add pixel format
    cmd.extend(['-pix_fmt', pixel_format])
    
    # Add any extra parameters
    cmd.extend(extra_params)
    
    cmd.append(f'no-audio_{output_name}')
    
    return cmd

def testEncoder(encoder):
    """Test if an encoder is available"""
    try:
        result = subprocess.run(
            ['ffmpeg', '-hide_banner', '-encoders'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return encoder in result.stdout
    except:
        return False

def processVideo(settings):
    input_name = settings["input_name"]

    if settings["cv_colourfix"]:
        colourFix(input_name)

    input_video = cv.VideoCapture(input_name)

    if input_video is None or not input_video.isOpened():
        raise VideoReadError()

    output_name = settings["output_name"]
    output_fps = settings["output_fps"]
    blend_mode = settings["blend_mode"]
    blend_range = float(settings["blend_range"])
    input_res = [int(input_video.get(cv.CAP_PROP_FRAME_WIDTH)),
                 int(input_video.get(cv.CAP_PROP_FRAME_HEIGHT))]
    output_res = parseResolution(input_res,settings["resolution"])
    input_fps = round(input_video.get(cv.CAP_PROP_FPS))
    output_fps = int(output_fps)
    fps_ratio = float(input_fps/output_fps)

    if fps_ratio < 1:
        raise Exception("ERROR - Output FPS is higher than input FPS, try lowering the output FPS using '-fps' argument")

    if input_fps % output_fps != 0:
        print("WARNING - Input FPS is not divisible by output FPS, this may cause the output video to be out of sync with the audio")
        print("Would you like to continue? (y/n)")
        choice = input()
        if choice != "y":
            raise Exception("User aborted")

    fps_ratio = int(fps_ratio)
    input_nframes = input_video.get(cv.CAP_PROP_FRAME_COUNT)
    output_nframes = int(input_nframes/fps_ratio)

    print(f"Input Res : {input_res}\nOutput Res : {output_res}")

    blended_nframes = int(blend_range*fps_ratio)
    weights = weight(blend_mode, blended_nframes)

    # Check if we should use FFmpeg encoder or OpenCV
    use_ffmpeg_encoder = settings.get("use_ffmpeg_encoder", False)
    encoder_settings = settings.get("encoder_settings", {})
    
    if use_ffmpeg_encoder:
        # Test if encoder is available
        encoder = encoder_settings.get("encoder", "libx264")
        print(f"Using FFmpeg encoder: {encoder}")
        
        if not testEncoder(encoder):
            print(f"WARNING: Encoder '{encoder}' not available, falling back to libx264")
            encoder_settings["encoder"] = "libx264"
        
        # Build FFmpeg command
        ffmpeg_cmd = buildEncoderCommand(encoder_settings, output_res, output_fps, output_name)
        
        # Start FFmpeg process
        try:
            ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except Exception as e:
            raise Exception(f"Failed to start FFmpeg encoder: {e}")
        
        output_writer = ffmpeg_process
    else:
        # Use OpenCV VideoWriter (old method)
        fourcc_code = settings["fourcc"]
        print(f"Using OpenCV VideoWriter with fourcc: {fourcc_code}")
        output_writer = cv.VideoWriter(
            filename=f"no-audio_{output_name}",
            fourcc=cv.VideoWriter_fourcc(*fourcc_code),
            fps=int(output_fps),
            frameSize=(output_res[0], output_res[1])
        )

    needResize = False
    if input_res != output_res:
        needResize = True

    time_list = [0]*15

    imgs = []
    input_video.set(cv.CAP_PROP_POS_FRAMES, 0)

    # First iteration, load all frames needed
    for _ in range(0, blended_nframes):
        _, frame = input_video.read()
        if needResize:
            frame = cv.resize(frame, (output_res[0], output_res[1]))
        imgs.append(frame)

    blended_frame = blend(np.asarray(imgs), weights)
    
    if use_ffmpeg_encoder:
        ffmpeg_process.stdin.write(blended_frame.tobytes())
    else:
        output_writer.write(blended_frame)
    
    del imgs[:fps_ratio]

    # Next iteration, load remaining unloaded frames
    for i in range(1, int(output_nframes)):
        timer_start = time.process_time()
        for _ in range(0, fps_ratio):
            _, frame = input_video.read()
            if needResize:
                frame = cv.resize(frame, (output_res[0], output_res[1]))
            imgs.append(frame)

        blended_frame = blend(np.asarray(imgs), weights)
        
        if use_ffmpeg_encoder:
            try:
                ffmpeg_process.stdin.write(blended_frame.tobytes())
            except BrokenPipeError:
                print("ERROR: FFmpeg encoder crashed")
                stderr = ffmpeg_process.stderr.read().decode()
                print(f"FFmpeg error: {stderr}")
                sys.exit(1)
        else:
            output_writer.write(blended_frame)
        
        del imgs[:fps_ratio]

        elapsed_time = (time.process_time()-timer_start)
        time_list.pop(0)
        time_list.append(elapsed_time)
        avg_time = sum(time_list)/len(time_list)

        print("\nPerformance  :", '%.3f' % (avg_time),
              "seconds/frame -", '%.3f' % (1/avg_time), "FPS")
        print("Estimation   :", time.strftime('%H:%M:%S',
              time.gmtime(math.ceil(avg_time*int(output_nframes-i)))))
        print(f"Progress     : {i}/{output_nframes} - ",
              '%.3f' % (100*i/output_nframes), "%")
    
    # Clean up
    if use_ffmpeg_encoder:
        ffmpeg_process.stdin.close()
        ffmpeg_process.wait()
        
        # Check for errors
        if ffmpeg_process.returncode != 0:
            stderr = ffmpeg_process.stderr.read().decode()
            print(f"FFmpeg encoding failed: {stderr}")
            sys.exit(1)
    else:
        output_writer.release()
    
    input_video.release()
    addAudio(input_name, output_name)

    if settings["cv_colourfix"]:
        os.remove(input_name)
        os.rename(f"to-fix_{input_name}", f"{input_name}")
        
def main():
    settings = loadSettings()
    
    processVideo(settings)

if __name__ == "__main__":
    main()
