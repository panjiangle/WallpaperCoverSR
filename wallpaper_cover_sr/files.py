import shutil


def replace_file(source, target):
    """Atomic on normal disks; tolerate redirected Windows profile folders."""
    try:
        source.replace(target)
    except OSError as exc:
        if getattr(exc, 'winerror', None) != 17:
            raise
        shutil.copyfile(source, target)
        source.unlink()
