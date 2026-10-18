# Third-party components

The MIT license in this repository applies to the bridge and settings UI only.
Models, the inference program and other dependencies retain their own licenses.

- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN), Xintao Wang et al.: BSD 3-Clause. The official 20220424 Windows NCNN release supplies the executable and model weights.
- [Real-ESRGAN-ncnn-vulkan](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan): retain the upstream license supplied in `licenses/backend` in portable builds.
- [ncnn](https://github.com/Tencent/ncnn): BSD 3-Clause; used by the upstream executable.
- [libwebp](https://github.com/webmproject/libwebp): upstream COPYING; used by the upstream executable.
- `vcomp140.dll`: Microsoft OpenMP runtime shipped in the official backend archive; it is a Microsoft component and is not covered by this project's MIT license.
- Python: Python Software Foundation license. Pillow, pystray, six, PyWinRT and PyInstaller retain their distribution licenses; the build copies available license files into `licenses`.

The backend downloader pins the official archive by URL and SHA256. It never downloads executables from third-party mirrors. Keep these notices and the `licenses` directory when redistributing a portable package.

Wallpaper art, album covers and music-player data are **not** included in this repository or release archive. Version 0.2 publishes artwork through Windows media controls and does not modify or redistribute wallpaper files. Ownership remains with their respective authors.
