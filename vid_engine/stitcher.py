import os
import subprocess
import imageio_ffmpeg

def stitch_scenes(episode_dir, output_file):
    """
    Takes a directory of scene videos and stitches them in order using 
    the portable FFmpeg binary from imageio-ffmpeg.
    """
    scenes = sorted([f for f in os.listdir(episode_dir) if f.endswith('.mp4')])
    
    if not scenes:
        print("No scenes found to stitch.")
        return

    # Create temporary concat list for FFmpeg
    list_file = "concat_list.txt"
    with open(list_file, "w") as f:
        for scene in scenes:
            # Full path and forward slashes for FFmpeg consistency
            path = os.path.abspath(os.path.join(episode_dir, scene)).replace("\\", "/")
            f.write(f"file '{path}'\n")

    print(f"Stitching {len(scenes)} scenes into {output_file}...")
    
    # Get the portable FFmpeg executable path
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    cmd = [
        ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", 
        "-i", list_file, "-c", "copy", output_file
    ]
    
    try:
        subprocess.run(cmd, check=True)
        print("[SUCCESS] Movie assembled successfully!")
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] FFmpeg failed: {e}")
    finally:
        if os.path.exists(list_file):
            os.remove(list_file)

if __name__ == "__main__":
    # Example usage
    stitch_scenes("vid_studio/output", "final_movie.mp4")
