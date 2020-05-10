fixmp4
======

Patrick Wagstrom &lt;patrick@wagstrom.net&gt;

May 2020

Overview
--------

All the time at home has given me a chance to do more work on a few projects sitting on my backlog. Notably, organizing my media library. I had noticed that many of the videos I created were stuttering in Plex when played back on my Apple TV (either 4th generation or 4k). After a lot of digging, a notable sign of this was because most of the videos did not have `reqiredBandwidth` in their XML within Plex. This would result in Videos churning back and forth between a few tenths of seconds of playing and buffering - even when then AppleTV was connected through a 1GBps hardwred ethernet link.

While I haven't been able to figure out the root cause of this or find a way to diagnose it ahead of time, I have found that it take the existing video and repackage it using `ffmpeg` that it works. Specifically, this command will create a new video without re-encoding everything:

```bash
ffmpeg -v warning -i INPUT_FILE.mp4 -c copy -map 0 OUTPUT_FILE.mp4
```

But, with so many videos, I wanted to make sure that I do this in a principled way and that I don't do it too many times and that I get some sense of progress while it is running. This, `fixmp4` was created.

Installation
------------
This project uses [`pipenv`](https://pipenv.pypa.io/en/latest/) to manage dependencies. It should work with most (any?) version of Python 3.

```bash
pipenv sync
```

You'll also need to have a fairly recent version of `ffmpeg` installed.

Usage
-----
Use `pipenv` to run the program.

```bash
pipenv run python fixmp4.py [TARGET_DIRECTORY]
```

If `TARGET_DIRECTORY` is omitted, `fixmp4` will work in the current directory.

FAQ
---

**Q:** Why doesn't `fixmp4` delete the old files?<br/>
**A:** I don't fully trust it yet to not do anything stupid. In particular, I don't think this does a great job handling error codes from `ffmpeg`.

**Q:** Why does this application crash on my RaspberryPi / FreeBSD / Minix / TRS-80 machine?<br/>
**A:** Most likely this is because of `ffmpeg`. It neesds a recent version and it appears that recent version works best on X86_64 Linux or X86_64 Mac OS systems. I just know it doesn't work ARM.

Bugs
----

Probably.

License
-------

Licensed under terms of the MIT License.
