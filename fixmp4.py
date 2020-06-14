#!/usr/bin/python3
"""Fix problems with improperly encoded video files.

For some reason a lot of my video files do not have proper
encoding and this results in errors during playback. This
script goes through each of the files uses ffmpeg to convert
the file to one that is wrapped appropriately.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import tempfile
import subprocess
import sys

from multiprocessing import Process

from typing import Dict, Any, List

from tqdm import tqdm

import coloredlogs
import logging

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)
coloredlogs.install(level="DEBUG", logger=logger)

MD5_BLOCKSIZE = 4 * 1024
MONITOR_DELAY = 1.0
STATUS_COMPLETE = "complete"


def md5(fname: str, desc: str = None) -> str:
    """Calculate the md5 sum of a large file.

    see: https://stackoverflow.com/a/3431838/57626
    """
    hash_md5 = hashlib.md5()
    if desc is None:
        desc = f"md5 {os.path.basename(fname)}"
    with tqdm(
        total=os.path.getsize(fname), unit="B", unit_scale=True, miniters=1, desc=desc, leave=False,
    ) as pbar:
        with open(fname, "rb") as f:
            ctr = 0
            for chunk in iter(lambda: f.read(MD5_BLOCKSIZE), b""):
                pbar.update(len(chunk))
                hash_md5.update(chunk)
                ctr = ctr + 1
    return hash_md5.hexdigest()


def get_ffmpeg_version() -> str:
    """Invoke ffmpeg to return the version string

    I found that weird things were happening in the program and that some of
    these issues might've been from different ffmpeg versions. This allows the
    program to fetch the ffmpeg version and record it later.
    """

    outcommand = [
        "ffmpeg",
        "-version",
    ]
    logger.info("command: %s", " ".join(outcommand))
    result = subprocess.run(outcommand, capture_output=True)
    return result.stdout.decode("utf-8")


def get_blocked_streams(filename: str) -> List[str]:
    """Get a list of streams that are eia_608.

    These are typically closed captioning tracks, but they're not officially
    supported in mp4 containers and it turns out that these tracks have been
    the problematic streams.

    This method coule be easily expanded to add additional codecs by adding
    them to the `BLOCKED_CODECS` list.
    """
    BLOCKED_CODECS = ["eia_608"]

    outcommand = ["ffprobe", "-show_streams", "-of", "json", filename]
    logger.info("command: %s", " ".join(outcommand))
    result = subprocess.run(outcommand, capture_output=True)

    if result.returncode != 0:
        logger.fatal("ffprobe exit code is %d - this indicates an error", result.returncode)
        sys.exit(1)

    out_streams = []  # type: List[str]
    for stream in json.loads(result.stdout.decode("utf-8")).get("streams", []):
        if stream.get("codec_name", "") in BLOCKED_CODECS:
            out_streams.append(f"0:{stream.get('index')}")
    return out_streams


def process_dir(dirname: str) -> None:
    """Iterate and process the video in a directory."""
    logger.info("processing: %s", dirname)

    basename = os.path.basename(dirname)
    json_metafile = os.path.join(dirname, f"{basename}.json")
    json_metadata = {}  # type: Dict[str, Any]

    # check to see if JSON metadata is present
    if os.path.isfile(json_metafile):
        logger.info("metafile '%s' is present", json_metafile)
        json_metadata = json.load(open(json_metafile))

    if json_metadata.get("status", "") == STATUS_COMPLETE:
        logger.info("%s is complete", dirname)
        return

    files = [x for x in os.listdir(os.path.join(dirname))]

    videos = [x for x in files if os.path.splitext(x)[1].lower() in [".m4v", ".mp4"]]

    if len(videos) == 0:
        logger.warn("no video files present")
        return

    if len(videos) > 1:
        logger.warn("multiple video files: %s", videos)
        return

    video = videos[0]
    logger.info("working on %s", video)

    # calculate md5sum of original file
    if "md5" not in json_metadata.get("original", {}):
        md5sum = md5(os.path.join(dirname, video), desc=f"original md5 {video}")
        json_metadata["original"] = {
            "filename": video,
            "md5": md5sum,
        }

    with open(json_metafile, "w") as f:
        json.dump(json_metadata, f)

    # run the conversion command
    outfilename = next(tempfile._get_candidate_names()) + ".mp4"

    blocked_tracks = get_blocked_streams(os.path.join(dirname, video))
    logger.info("eia_608 tracks: %s", blocked_tracks)

    def transcode():
        logger.info("writing remuxed file to: %s", outfilename)
        outcommand = [
            "ffmpeg",
            "-v",
            "warning",
            "-i",
            os.path.join(dirname, video),
            "-c",
            "copy",
            "-map",
            "0",
        ]
        for track in blocked_tracks:
            outcommand = outcommand + ["-map", f"-{track}"]
        outcommand.append(os.path.join(dirname, outfilename))
        logger.info("command: %s", " ".join(outcommand))
        subprocess.run(outcommand, stdout=sys.stdout.buffer, stderr=sys.stdout.buffer)

    json_metadata["ffmpeg"] = get_ffmpeg_version()

    p = Process(target=transcode)
    p.start()

    with tqdm(
        total=os.path.getsize(os.path.join(dirname, video)),
        unit="B",
        unit_scale=True,
        miniters=1,
        desc=f"ffmpeg {video}",
        leave=False,
    ) as pbar:
        old_filesize = 0
        while True:
            p.join(MONITOR_DELAY)
            if os.path.isfile(os.path.join(dirname, outfilename)):
                filesize = os.path.getsize(os.path.join(dirname, outfilename))
                pbar.update(filesize - old_filesize)
                old_filesize = filesize
            if p.exitcode is not None:
                break

    logger.warning("exitcode %d", p.exitcode)
    # get the final filesize of the output filename
    if os.path.getsize(os.path.join(dirname, outfilename)) == 0:
        os.remove(os.path.join(dirname, outfilename))
        logger.fatal("Converstion error - output file size of %s is 0 bytes", outfilename)
        sys.exit(1)

    json_metadata["new"] = {"filename": outfilename}

    # incrementally save the metadata
    with open(json_metafile, "w") as f:
        json.dump(json_metadata, f)

    logger.info("calculating remuxed md5")
    md5sum = md5(os.path.join(dirname, outfilename), desc=f"converted md5 {video}")
    json_metadata["new"]["md5"] = md5sum

    # rename the files
    original_moved = video + ".orig"
    os.rename(os.path.join(dirname, video), os.path.join(dirname, original_moved))
    json_metadata["original"]["target"] = original_moved

    new_moved = os.path.join(dirname, os.path.basename(dirname) + ".mp4")
    os.rename(os.path.join(dirname, outfilename), new_moved)
    logger.info("renamed %s to %s", os.path.join(dirname, outfilename), new_moved)
    json_metadata["new"]["target"] = os.path.basename(new_moved)

    # add in the metadata to show when the task was completed
    # this stores the timestamp as an int and an isoformat string with timezone
    completion_time = datetime.datetime.now(datetime.timezone.utc)
    json_metadata["status"] = STATUS_COMPLETE
    json_metadata["timestamp"] = int(completion_time.timestamp())
    json_metadata["isotimestamp"] = completion_time.astimezone().isoformat(timespec="seconds")

    with open(json_metafile, "w") as f:
        json.dump(json_metadata, f)


def main(dirname: str = ".") -> None:
    """Iterate through all the directories.

    Because there isn't a way to know ahead of time if we need to look at the
    files in a directory, the directories are iterated through. This means that
    even junk directories are counted as part of the list.
    """

    if not (os.path.isdir(dirname)):
        logger.error("%s is not a directory", dirname)
        sys.exit(1)

    logger.info("working in directory %s", dirname)

    ansi = {"BOLD": "\033[1m", "RED": "\033[91m", "END": "\033[0m"}
    dirs = [
        os.path.join(dirname, x)
        for x in os.listdir(dirname)
        if os.path.isdir(os.path.join(dirname, x))
    ]
    dirs = sorted(dirs)
    for this_dir in tqdm(dirs, desc="{BOLD}{RED}Total Progress{END}".format(**ansi)):
        process_dir(this_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "dirname", action="store", default=os.getcwd(), nargs="?", help="directory to work within",
    )

    args = parser.parse_args()

    main(dirname=args.dirname)
