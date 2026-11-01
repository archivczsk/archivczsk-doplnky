# -*- coding: utf-8 -*-

import os

try:
    os.chmod(os.path.join(os.path.dirname(__file__), 'bin', 'exteplayer3'), 0o755)
    os.chmod(os.path.join(os.path.dirname(__file__), 'bin', 'ffmpeg'), 0o755)
except:
    pass
