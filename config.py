# -*- coding: utf-8 -*-

__all__ = ["Config"]


class Singleton(type):
    def __init__(cls, *args, **kwargs):
        cls.__instance = None
        super().__init__(*args, **kwargs)

    def __call__(cls, *args, **kwargs):
        if cls.__instance is None:
            cls.__instance = super().__call__(*args, **kwargs)
            return cls.__instance
        else:
            return cls.__instance


class Config(metaclass=Singleton):
    """Configuration class.
    This is a singleton class that contains all the configuration data
    shared by all the classes of the application.
    Initially all variables are initialized to None.
    """
    log_level = None
    input = None
    input_str = ""
    input_is_file = False
    database_path = None
    db = None
    itunes = False
    aac = False
    alac = False
    mp3 = False
    quality = 0
    dry_run = False
    no_db = False
    verbose = False
    debug = False
    ffmpeg = None
    qaac = None
    input_list = []
    aac_conversion_list = []
    alac_conversion_list = []
    mp3_conversion_list = []

    input_list_str = []
    output_aac_list = []
    output_aac_list_str = []
    output_alac_list = []
    output_alac_list_str = []
    output_mp3_list = []
    output_mp3_list_str = []

    def __repr__(self):
        return str(vars(self))

    def __str__(self):
        return self.__repr__()
