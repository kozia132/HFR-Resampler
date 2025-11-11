import argparse
import json
import sys
import os

def loadSettings():
    settingsJson = None
    with open("settings.json") as settings:
        settingsJson = json.load(settings)

    # Check if file was dragged onto the executable
    if len(sys.argv) == 2 and not sys.argv[1].startswith('-'):
        # Drag and drop mode
        input_file = sys.argv[1]
        
        # Verify the file exists
        if not os.path.exists(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")
        
        # Generate output filename
        filename_without_ext = os.path.splitext(input_file)[0]
        output_suffix = settingsJson.get("output_suffix", "_resampled")
        output_extension = settingsJson.get("output_extension", ".mp4")
        output_file = f"{filename_without_ext}{output_suffix}{output_extension}"
        
        print("=== DRAG AND DROP MODE ===")
        print(f"Input file: {input_file}")
        print(f"Output file: {output_file}")
        print(f"Using settings from settings.json")
        print("==========================\n")
        
        return {
            "input_name": input_file,
            "output_name": output_file,
            "output_fps": settingsJson["framerate"],
            "blend_mode": settingsJson["blend_mode"],
            "blend_range": settingsJson["blend_range"],
            "resolution": settingsJson["resolution"],
            "fourcc": settingsJson["fourcc"],
            "cv_colourfix": settingsJson["cv_colourfix"],
            "use_ffmpeg_encoder": settingsJson.get("use_ffmpeg_encoder", False),
            "encoder_settings": settingsJson.get("encoder_settings", {})
        }

    # Normal CLI mode
    args_parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)

    args_parser.add_argument("-i", "--input_name", required=True, type=str, 
                             help="""Name of the input file with extension.\
                                \nExample : -i vaxei_godmode.mp4""")

    args_parser.add_argument("-o", "--output_name", required=True, type=str, 
                             help="""Name of the output file with extension.\
                                \nExample : -o resampled_video.mkv""")

    args_parser.add_argument("-fps", "--output_fps", type=int, default=settingsJson["framerate"],
                             help="""Framerate/FPS of the output file.\
                                \nExample : -fps 60""")

    args_parser.add_argument("-m", "--blend_mode", type=str, default=settingsJson["blend_mode"],
                             help="""Choose blending mode. (Check the GitHub readme for more info)\
                                \nExample : -m GAUSSIAN_SYM, -m EQUAL""")

    args_parser.add_argument("-r", "--blend_range", type=float, default=settingsJson["blend_range"],
                             help="""Range or Blend Range is the number that you get from calculating how many frames are resampled divided by the ratio between input and output fps.\
                                \nTips : Use value between 1.0 - 2.0, above 3.5 will cause blurry effect. This will also impact resampling performance""")

    args_parser.add_argument("-res", "--resolution", type=str, default=settingsJson["resolution"],
                             help="""Resolution of the output video.\
                                \nExample : -res 1920x1080 , -res UNCHANGED""")

    args_parser.add_argument("-fourcc", "--fourcc_code", type=str, default=settingsJson["fourcc"],
                             help="""Choose what video codec you want to use by their respective FOURCC code (only used with OpenCV encoder)\
                                \nExample : -fourcc MJPG""")

    args_parser.add_argument("-cvfix", "--cv_colourfix", action='store_true', default=settingsJson["cv_colourfix"],
                             help="""Enable this if you're resampling video produced by osr2mp4.\
                                \nExample : -cvfix""")

    args_parser.add_argument("-encoder", "--encoder", type=str, default=None,
                             help="""Specify encoder to use. Options: libx264, libx265, h264_nvenc, hevc_nvenc, h264_qsv, hevc_qsv, h264_amf\
                                \nExample : -encoder h264_nvenc""")

    args_parser.add_argument("-preset", "--preset", type=str, default=None,
                             help="""Encoder preset (fast, medium, slow, etc.)\
                                \nExample : -preset fast""")

    args_parser.add_argument("-crf", "--crf", type=int, default=None,
                             help="""Quality setting (lower = better quality, 0-51 for x264/x265, 0-51 for NVENC)\
                                \nExample : -crf 18""")

    args_parser.add_argument('--version', action='version', version='HFR-Resampler v0.5 (Custom Encoder Support)')

    parsed_args = args_parser.parse_args()

    # Determine if we're using FFmpeg encoder
    use_ffmpeg_encoder = settingsJson.get("use_ffmpeg_encoder", False)
    encoder_settings = settingsJson.get("encoder_settings", {})

    # Override encoder settings from command line if provided
    if parsed_args.encoder is not None:
        use_ffmpeg_encoder = True
        encoder_settings["encoder"] = parsed_args.encoder
    
    if parsed_args.preset is not None:
        encoder_settings["preset"] = parsed_args.preset
    
    if parsed_args.crf is not None:
        encoder_settings["crf"] = parsed_args.crf

    return {
        "input_name": parsed_args.input_name,
        "output_name": parsed_args.output_name,
        "output_fps": parsed_args.output_fps,
        "blend_mode": parsed_args.blend_mode,
        "blend_range": parsed_args.blend_range,
        "resolution": parsed_args.resolution,
        "fourcc": parsed_args.fourcc_code,
        "cv_colourfix": parsed_args.cv_colourfix,
        "use_ffmpeg_encoder": use_ffmpeg_encoder,
        "encoder_settings": encoder_settings
    }
