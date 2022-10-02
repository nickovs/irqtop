# irqtop

`irqtop` is a tool to display live information about the rate of
interrupts from the available interrupt sources in a Linux system.


## Installation and dependencies

`irqtop` is written in Python and requires Python 3.7 or later, but
has no other dependencies. It is distributed as a single Python file.
Install it by copying it to some directory on your `PATH` and
setting the executable bit, e.g.:
```shell
cp irqtop.py /usr/local/bin/irqtop
chmod +x /usr/local/bin/irqtop
```


## Usage

By default `irqtop` will try to display each interrupt name/ID, the total number of
interrupts per second from each source, the number of interrupts going to each
CPU for each source, and device name or source description. These are all sorted
by total interrupt rate, updated once per second, and will be refreshed
indefinitely until the program is halted.

If the program is run on an interactive terminal (`tty`) then it tries to fit
the display to the space available. To achieve this, the number of lines
displayed is limited to the vertical height of the display, the set of
displayed CPUs may be limited to fit the width and the device details for each
interrupt may be trimmed or omitted. How this is handled can be controlled
using the command line options as follows:

  `--filter REGEX`, `-f REGEX`: Only display IRQs who's ID or device description
  match the provided regular expression.

  `--total`, `-t`: Only display the total interrupt count, not per CPU counts.
  
  `--no-total`: Hide the total

  `--details`, `--device`, `-d`: Force display of device details, at the
expense of potentially not displaying some CPUs' interrupt counts.

  `--no-details`, `--no-device`: Hide the device details, even if there is room.

  `--cpus CPUS`, `-c CPUS`: Only display interrupt counts for the listed CPUs.
  
  `--sort ORDER`, `-s ORDER`: Sort by (t)otal count, (n)ame or (d)evice.
  Use the upper case letter to reverse the order.

  `--interval N`, `-i N`: Sample every N seconds (may be a floating point value).

  `--count N`, `-n N`: Update the results N times and then exit.

## Interactive filtering

It is often useful to change the options and filtering of the display contents
while `irqtop` is running. The following keys can be used to control the
program after it has started:
* `f` followed by a filter regex to update the filtering. A blank entry removes
any existing filter.
* `t` toggles the display of the total interrupt count.
* `d` toggels the display of the device details. Use `D` to include the details
if there is room but hide them otherwise.
* `c` followed by a list of CPU numbers or ranges to change the set of CPUs for
which the count is displayed. Use '+' to display all CPUs, '-' to display none 
of the CPUs and a blank entry to revert to the command line option settings.
* `i` followed by a number (in seconds) to set the refresh interval.
* `q` to quit the program.

## License

`irqtop` is released under the [MIT License](https://opensource.org/licenses/MIT).


## Credits

`irqtop` was written by Nicko van Someren. It was inspired by an earlier
program written in Perl called [itop](https://github.com/kargig/itop) written
by [George Kargiotakis](https://github.com/kargig). I find that Pearl is
largely incomprehensible, and in general it's a good idea to be able to
understand your system tools, so I built a new version in Python instead.



