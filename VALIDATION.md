# Validation scope — 0.3.1

2026-10-18, Windows 11 x64, Wallpaper Engine 2.8.42, RTX 4070 SUPER, NetEase 3.1.41.205529. This is single-machine validation, not a cross-hardware certification.

## 0.3.1 recovery update — 2026-10-19

The old metadata-only reclaim call failed to restore Windows' current media session after another manual SMTC publisher became current. Closing and recreating the enhanced MediaPlayer restored selection on this host. The worker now performs this only when its selected real source is current, checks that song and settings are still valid, and reuses the already processed PNG. Recovery is limited to once per two seconds while the source keeps reclaiming; unrelated current players retain normal source-selection behavior.

A regression test at the actual worker loop failed before the fix and passed afterward. The suite now has 30 passing checks, including unchanged-cover takeover, unrelated-player handoff, recovery throttling, song changes and disable during recovery. A separate native Windows process published a manual source session carrying actual player metadata/artwork. Its takeover was explicitly observed before each recovery; recreating the enhanced MediaPlayer then restored Windows selection on three successive takeovers. The worker-loop regression separately verifies reuse of the processed PNG without another cover-processing call. These are synthetic takeover checks on one machine, not a guarantee of recovery latency across systems.

## Original 0.3.0 validation

## New original-artwork path

The source lookup reads the local NetEase playingList JSON and matches SMTC title, artist and album when supplied. Downloads are restricted to HTTPS public NetEase picture hosts and checked against the actual system thumbnail by low-resolution RGB difference and grayscale correlation. No search service, account cookie or player injection is used.

Three real 135×135 source covers matched official originals of 3508×3508, 1832×1832 and 1500×1500. The production cover pipeline published 1024×1024 PNG display copies, without AI inference. In this check the AI function was replaced with a failing guard, so invoking it would have failed the check. Fresh original fetch/decode/display-copy preparation took 0.809, 0.748 and 0.258 seconds respectively. Each subsequent cache read passed with network fetch replaced by a failing guard.

Twenty-five automated checks passed: previous media routing/cache/cancellation checks, no-inference HD path, cache reuse/revalidation, wrong artist/album/image rejection, lead-artist-only collaboration matching, ambiguous versions, disabled online path, network-failure fallback, fetch cancellation, unsupported playlist data, rejected foreign/credentialed/ported URLs and foreign redirects, and inability of blank thumbnails to establish identity. These tests are limited fixtures and do not establish a universal false-match rate for album art.

The HD path caps display output at a 1024-pixel long edge, retains originals' dimensions in cache metadata and never upscales this output. It shares the existing 128MiB approximate PNG cache budget. Original raw CDN image bytes are not retained by the production cache. Failed HD resolution retries at a bounded interval while preserving verified output for the same song.

Live UI callbacks passed original → offline super-resolution → original → disabled → original. The real OS media path also passed 2×/3×/4× fallback dimensions, exact title/artist, disabled restoration and exit/session removal. A real collaboration whose SMTC metadata exposes only the lead artist also resolved its 2048×2048 original correctly.

Final portable application passed a fresh uncached official-CDN HTTPS fetch: 3000×3000 original → 1024×1024 display copy in 0.582 s, with cache_hit=false, model=none and artwork_source=netease-original. A separate process verified that the live Windows media thumbnail bytes exactly matched the output PNG, and that title/artist matched the real player. The original 3395777145 scene also displayed this real original artwork in a temporary native preview; the preview was closed and the user's existing wallpaper selection retained. Settings window layout was visually checked.

A 24.02-second helper-process sample with settings visible and a brief native wallpaper preview measured 0.1406 CPU-seconds (0.0293% average total CPU across 20 logical cores) and 90.66 MiB working set. No inference process remained. This short usage sample is not a pure idle soak test and excludes the player's/Wallpaper Engine's resource use. The portable archive remains approximately 61.3 MiB and includes no Nomos/ONNX/PyTorch runtime or experimental artwork.

## Existing bridge and fallback

The unchanged Windows SMTC bridge supports original scene wallpaper media textures without modifying wallpaper files. In 0.2 it passed native renderer checks for original workshops 3571726810 and 3395777145, including current/previous texture effects. It also passed live pause/resume forwarding, paused-startup selection, disabled/exit session removal, and exact published PNG byte checks. A web-wallpaper preview experiment failed on this host with a native engine error; web compatibility remains unverified. The user's original scene was restored.

The offline fallback remains official Real-ESRGAN x4plus NCNN. Native inference is 4×; 2×/3× resize its cached output. No ML framework or Nomos trial dependency is added to the portable runtime. No inference child remains after processing.

## Limits

NetEase's local queue format is undocumented and verified only on the named desktop version. Unrecognized versions, stores, local tracks, missing metadata, nearly flat artwork, ambiguity or mismatched art fall back instead of guessing. Conservative matching may reject valid covers. Different simultaneous players, other GPUs, multiple physical monitors, fresh Windows media/Vulkan installations and a real reboot are not newly validated. Startup waiting/retry remains implemented. Network timings depend on connectivity; disabling HD restores the offline path. No wallpaper package parsing or monitor-specific integration is introduced.
