import subprocess
from os import chdir, getcwd
from typing import TypedDict, Optional, Union

from ..utils import logger
from .error import ConfigError, CommandError


def check_subprocess_status(status: subprocess.CompletedProcess):
    """
    Check subprocess return code and print log if ``return_code != 0``.

    :param status: Status from subprocess.
    :type status: CompletedProcess
    """
    if status.returncode != 0:
        # print command
        command = status.args
        logger.error(f"Failed to exec command: {command}")

        # print log
        logger.error("====== stdout ======")
        logger.error(status.stdout.decode())
        logger.error("====== ====== ======")
        logger.error("====== stderr ======")
        logger.error(status.stderr.decode())
        logger.error("====== ====== ======")

        # raise error
        raise RuntimeError


def call_subprocess(command: list[str], work_path: Optional[str] = None, print_output=False):
    """
    Execute the given command in system shell.

    :param command: A list contains the command and parameters to be executed.
    :type command: list
    :param work_path: The work path of the command.
                      If None, works in current directory.
    :type work_path: str | None
    :param print_output: If print standard output and error in the logger.
    :type print_output: bool
    :return:
    :rtype:
    """
    if work_path is not None:
        origin_path = getcwd()
        chdir(work_path)
    else:
        origin_path = None

    status = subprocess.run(' '.join(command), shell=True, capture_output=True)

    if origin_path is not None:
        chdir(origin_path)

    check_subprocess_status(status)

    if print_output:
        logger.info(status.stdout.decode())
        logger.warning(status.stderr.decode())


class ExecutableClassConfig(TypedDict):
    """
    Executable class initialization config template.
    """
    # only list essential config
    class_args: tuple
    class_kwargs: dict


class ExecutableConfig(TypedDict):
    """
    Executable config template.
    """
    name: str
    cmd: Union[str, list[str]]
    work_path: Optional[str]
    mpi_use: bool
    mpi_cmd: Optional[str]
    mpi_core_num: Optional[int]
    class_config: Optional[ExecutableClassConfig]
    custom_config: Optional[dict]


class ExecutableBase:
    """
    Base class for all executables.
    """
    _instance = None
    _initialized = False

    def __init__(self, name: str, cmd: Union[str, list[str]], work_path: Optional[str] = None, mpi_use=False, mpi_cmd: Optional[str] = None, mpi_core_num: Optional[int] = None):
        """
        Base class for all executables.

        :param name: Unique name to identify different executables.
        :type name: str
        :param cmd: Command to execute, can be a single string or a list contains the command and its parameters.
                    For example, ``"./geogrid.exe"``, ``["./link_grib.csh", "data/*", "."]``.
                    If you want to use mpi, then ``cmd`` must be a string.
        :type cmd: str
        :param work_path: Working directory path. Defaults to None (wrfrun workspace).
        :type work_path: str
        :param mpi_use: If you use mpi. You have to give ``mpi_cmd`` and ``mpi_core_num`` if you use mpi. Defaults to False.
        :type mpi_use: bool
        :param mpi_cmd: MPI command. For example, ``"mpirun"``. Defaults to None.
        :type mpi_cmd: str
        :param mpi_core_num: How many cores you use. Defaults to None.
        :type mpi_core_num: int
        """
        if self._initialized:
            return

        if mpi_use and isinstance(cmd, list):
            logger.error("If you want to use mpi, then `cmd` must be a single string.")
            raise CommandError("If you want to use mpi, then `cmd` must be a single string.")

        self.name = name
        self.cmd = cmd
        self.work_path = work_path
        self.mpi_use = mpi_use
        self.mpi_cmd = mpi_cmd
        self.mpi_core_num = mpi_core_num

        self.class_config: Optional[ExecutableClassConfig] = None
        self.custom_config: Optional[dict] = None

        self._initialized = True

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)

        return cls._instance

    def generate_custom_config(self):
        """
        Generate custom configs.
        Child class must implement this method to use the replay feature.

        :return:
        :rtype:
        """
        raise NotImplementedError

    def load_custom_config(self):
        """
        Load custom configs.
        Child class must implement this method to use the replay feature.

        :return:
        :rtype:
        """
        raise NotImplementedError

    def export_config(self) -> ExecutableConfig:
        """
        Export config of this executable.

        :return: A dict contains configs.
        :rtype: ExecutableConfig
        """
        self.generate_custom_config()

        return {
            "name": self.name,
            "cmd": self.cmd,
            "work_path": self.work_path,
            "mpi_use": self.mpi_use,
            "mpi_cmd": self.mpi_cmd,
            "mpi_core_num": self.mpi_core_num,
            "class_config": self.class_config,
            "custom_config": self.custom_config,
        }

    def load_config(self, config: ExecutableConfig):
        """
        Load config from a dict.

        :param config: Config dict. It must contain some essential keys. Check ``ExecutableConfig`` for details.
        :type config: ExecutableConfig
        :return:
        :rtype:
        """
        if "name" not in config:
            logger.error("A valid config is required. Please check ``ExecutableConfig``.")
            raise ValueError("A valid config is required. Please check ``ExecutableConfig``.")
        
        if self.name != config["name"]:
            logger.error(f"Config belongs to '{config['name']}', not {self.name}")
            raise ConfigError(f"Config belongs to '{config['name']}', not {self.name}")

        self.cmd = config["cmd"]
        self.work_path = config["work_path"]
        self.mpi_use = config["mpi_use"]
        self.mpi_cmd = config["mpi_cmd"]
        self.mpi_core_num = config["mpi_core_num"]
        self.class_config = config["class_config"]
        self.custom_config = config["custom_config"]

        self.load_custom_config()

    def replay(self):
        """
        This method will be called when replay the simulation.
        This method should take care every job that will be done when replaying the simulation.

        :return:
        :rtype:
        """
        raise NotImplementedError("If you want your executable supports replay feature, you must implement this method.")

    def __call__(self):
        """
        Execute the given command.

        :return:
        :rtype:
        """
        if not self.mpi_use or None in [self.mpi_cmd, self.mpi_core_num]:
            if isinstance(self.cmd, str):
                self.cmd = [self.cmd, ]

            logger.info(f"Running `{' '.join(self.cmd)}` ...")
            call_subprocess(self.cmd, work_path=self.work_path)

        else:
            logger.info(f"Running `{self.mpi_cmd} --oversubscribe -np {self.mpi_core_num} {self.cmd}` ...")
            call_subprocess([self.mpi_cmd, "--oversubscribe", "-np", str(self.mpi_core_num), self.cmd], work_path=self.work_path)


__all__ = ["ExecutableBase"]
