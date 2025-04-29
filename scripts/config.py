import configparser as cp
from typing import List, Optional


def read_config(sections: List[str], option: Optional[str], return_type: Optional[str]) -> str:
    """
    Read settings from config.ini.

    If not created, the settings are created with default values ​​and written to config.ini.

    :param List[str] sections: config sections to load.
    :param str option: config option to load.
        If option is None, all options in sections will be loaded.
    :param str return_type: config data type to return.
        If type is None or not supported, it will return string.

    :return str or else supported: config value.
        Type is determined by `return_type`.
    """
    global option_dict
    config = cp.ConfigParser()
    config.read('config.ini')
    needs_write = False

    ret = None  # init config returns nothing
    ret_type = ""
    ret_type_dict = {
        "int": "int",
        "float": "float",
        "double": "float",
        "boolean": "boolean",
        "bool": "boolean"
    }
    globals()[""] = config.get
    globals()["int"] = config.getint
    globals()["float"] = config.getfloat
    globals()["boolean"] = config.getboolean
    if return_type in ret_type_dict.keys():
        ret_type = ret_type_dict[return_type]

    for section in sections:
        if config.has_section(section) == False:
            config.add_section(section)
            needs_write = True
        if option is None:  # read all configs (for config init)
            options = list(option_dict[section].keys())
            option_defaults = list(option_dict[section].values())
        else:  # read 1 option from 1 section (for get config)
            options = [option]
            option_defaults = [option_dict[section][option]]
        for option_id in range(len(options)):
            if config.has_option(section, options[option_id]) == False:
                config.set(section, options[option_id], option_defaults[option_id])
                needs_write = True

    if needs_write:
        with open('config.ini', 'w') as configfile:
            config.write(configfile)
        configfile.close()

    if option is not None:  # specific config query needs a return value
        ret = globals()[ret_type](section, option)
    return ret


def write_config(section: str, option: str, value):
    """
    Write settings to config.ini.
    """
    config = cp.ConfigParser()
    config.read('config.ini')
    if (config.has_section(section) == False):
        config.add_section(section)
    config.set(section, option, str(value))

    with open('config.ini', 'w') as configfile:
        config.write(configfile)
    configfile.close()


"""
config module definition:
xx_section -> str: the name of xx config module
xx_options -> dict{str: str}: dict of xx option names and default values
"""

# Bench4BL config definition
Bench4BL_section = "Bench4BL"
Bench4BL_options = {
    "path": "./Bench4BL",
}

# data collection config definition
data_section = "data"
data_options = {
    "path": "../data",
}

# LLM config definition
LLM_section = "LLM"
LLM_options = {
    "api_key": "your_api_key",
    "base_url": "your_base_url",
}

# all config zip to dict
option_dict = {}
section_prefix = ["Bench4BL", "data", "LLM"]
section_suffix = "_section"
options_suffix = "_options"
for section_id in range(len(section_prefix)):
    option_dict.update({
        eval(section_prefix[section_id] + section_suffix):
            eval(section_prefix[section_id] + options_suffix)
    })

# init config
read_config(option_dict.keys(), None, None)
