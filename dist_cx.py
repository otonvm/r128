from cx_Freeze import setup, Executable

options = {
    'build_exe': {
        'packages': [],
        'includes': ['logger'],
        'excludes': [],
        'compressed': True,
        'include_files': ['ffmpeg/', 'qaac/']
    },
    'install_exe': {
        'force': True
    }
}

executables = [
    Executable('normalize.py', base='Console', targetName='normalize.exe')
]

setup(name='normalize',
      version = '1.0',
      description = 'Normalize FLAC files by EBU R128 specification',
      options = options,
      executables = executables
      )
