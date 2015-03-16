# Abstract #
This is a simple file monitoring daemon. It is configured with Event Definitions that basically say which file patterns the daemon should react on, and what the resulting action should be.

# Features #
  * Pure Python
  * Works without inotify (Linux only) on Windows, Unix and Linux OSes.
  * Uses "modified"  stat() metadata and file size comparison to detect if a file is closed / fully written to disk. If the file size does not change within a tracking interval, it is considered to be closed (of course it depends on the application when the file is closed, so this parameter needs to be configured per-Event Definition)
  * Can be configured to reload its config file dynamically
  * Event Definitions that have a (repeatedly) failing Action can be disabled automatically
  * One Python file and one YAML config file; easy to deploy or modify

# Dependencies #
  * Python > 2.6
  * PyYAML

# Usage #
```
Usage: monitor.py
          [-t|--test]             : Run test mode (use this to create a sample config file)
          [-i N|--interval=N]     : Polling interval of N seconds [5]
          [-c file|--config=file] : Use YAML config file [config.yaml]
          [-d|--dynamic]          : Enable dynamic config file reload
          [-v|--verbose]          : Print debug messages
          [-h|--help]             : Print this help message
          [-l|--logging]          : Enable file logging, default is console only
          [--backupcount=N]       : Keep N logfiles (rotate) [5]
          [--logfilesize=N]       : Rotate logfile when N bytes in size [100000]
          [--logfilename=file]    : Log file name [monitor.out]
```

## Actions ##

When defining actions, you can reference the event and its definition by enclosing them in curly braces, for example to reference the directory (eventdef.dir) and the actual file name (event.filename):

```

- !!python/object:__main__.EventDef {
        action: 'echo "{eventdef.dir}" >> /tmp/hallo.out; ls -l /tmp/{event.filename}', 
        dir: /tmp, 
        maxerrors: 2, 
        minsize: 0, 
        pattern: hallo.*\.txt,
        tracking_interval: 60
   }

```

The following properties can be defined:

  * `action`: The command that should be executed if the file is detected.
  * `dir`: The directory that is monitored for new files.
  * `maxerrors`: The `action` is executed that much times if it yields an error (exit status other that 0)
  * `minsize`: Event will only be triggered if the file size is larger than this parameter (in bytes)
  * `tracking_interval`: the file is checked every `tracking_interval` seconds if it changed (to determine if it is closed or still written to).


