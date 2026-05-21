# Linux Basics for the USB Defense Project

A beginner-friendly Linux primer focused on what you need for this project.
Read this once before installing Rocky Linux. Come back to it whenever you're stuck.

---

## 1. What is Linux?

Linux is an operating system, like Windows or macOS — but with key differences:

- **It's free and open source.** Anyone can use, modify, redistribute it.
- **It runs most of the world's servers.** Banks, defense systems, ISRO, Google, Netflix, Indian Railways — all on Linux.
- **You control everything via the terminal.** GUI exists, but power users live in the command line.
- **Distributions ("distros")** are flavors of Linux: Ubuntu, Fedora, Rocky Linux, Kali, Debian. Same kernel underneath, different packaging.

We're using **Rocky Linux 9** because it's identical to Red Hat Enterprise Linux (RHEL), which is the actual OS used by Indian defense and enterprise systems.

---

## 2. The Terminal

Open the terminal in Rocky Linux: search "Terminal" in the Activities menu, or press `Ctrl+Alt+T`.

You'll see a **prompt** like:
```
[username@hostname ~]$
```

- `username` — your Linux user
- `hostname` — the computer's name
- `~` — current directory (`~` is shorthand for "your home folder")
- `$` — means a regular user. `#` means root (admin).

You type commands here and press Enter.

---

## 3. The File System

Linux has **one root directory** (`/`), unlike Windows which has `C:\`, `D:\`, etc. Everything lives under `/`.

Important folders:

| Path | What it is |
|---|---|
| `/` | Root. Top of the tree. |
| `/home/username/` | Your personal files. Same as `~`. Like `C:\Users\KIIT` on Windows. |
| `/etc/` | System configuration files. |
| `/var/log/` | System logs go here. |
| `/usr/bin/` | Installed programs (executables). |
| `/tmp/` | Temporary files. Cleared on reboot. |
| `/root/` | The root user's home folder. |
| `/dev/` | Device files (USBs show up here as `/dev/sdb`, `/dev/sdc`, etc.) |
| `/media/` and `/mnt/` | Mounted USB drives appear here. |

---

## 4. Essential Commands

### Navigation

```bash
pwd                  # print working directory (where am I?)
ls                   # list files in current directory
ls -l                # list with details (size, date, permissions)
ls -la               # list including hidden files (starting with .)
cd Documents         # change directory into Documents
cd ..                # go up one level
cd ~                 # go home
cd /                 # go to root
```

### File operations

```bash
cat file.txt              # show file contents
less file.txt             # show file scrollably (press q to quit)
head file.txt             # show first 10 lines
tail file.txt             # show last 10 lines
tail -f /var/log/syslog   # show last lines, then follow as they update
cp source dest            # copy
mv source dest            # move or rename
rm file.txt               # DELETE file (no recycle bin — gone forever!)
rm -r folder/             # delete folder and everything in it
mkdir newfolder           # make new directory
touch newfile.txt         # create empty file
```

### Important: there is NO recycle bin in Linux. `rm` deletes immediately and permanently.

### Searching

```bash
find / -name "*.iso"            # find all .iso files starting from /
grep "error" /var/log/messages  # find lines containing "error" in a file
grep -r "TODO" /home/me/code    # search recursively
```

### System info

```bash
whoami           # which user am I?
hostname         # what's this machine called?
uname -a         # kernel and system info
df -h            # disk usage (human readable)
free -h          # RAM usage
top              # live process viewer (press q to quit)
ps aux           # list all processes
```

---

## 5. The Magic Word: `sudo`

Most system-level operations (installing software, editing system files, controlling services) need **root privileges**. You don't log in as root — instead, you prefix commands with `sudo`:

```bash
sudo dnf install python3       # install software (needs admin)
sudo systemctl start usbguard  # start a service (needs admin)
sudo nano /etc/hosts           # edit a system file (needs admin)
```

`sudo` will ask for **your** password the first time, then remember for ~15 minutes.

> Think of `sudo` as "Run As Administrator" in Windows.

---

## 6. Installing Software (dnf)

Rocky Linux uses **dnf** as its package manager. (Ubuntu uses `apt`, Arch uses `pacman` — different distros, different tools, same idea.)

```bash
sudo dnf install python3              # install python3
sudo dnf install python3 git nano     # install multiple at once
sudo dnf remove python3               # uninstall
sudo dnf update                       # update all installed packages
sudo dnf search keyword               # search for available packages
sudo dnf list installed               # list what's installed
dnf info python3                      # info about a package
```

**For our project, you'll run things like:**
```bash
sudo dnf install python3 python3-pip git usbguard
sudo pip3 install pyqt5 pyudev
```

---

## 7. File Permissions

Every file has three sets of permissions:
- **Owner** (the user who owns it)
- **Group** (a group of users)
- **Others** (everyone else)

Each can have **read (r), write (w), execute (x)** permissions.

When you run `ls -l`, you see something like:
```
-rwxr-xr-- 1 ratnesh users 1234 May  5 14:30 myscript.sh
```

Decoded:
- `-` = regular file (`d` = directory)
- `rwx` = owner can read/write/execute
- `r-x` = group can read/execute (not write)
- `r--` = others can only read

To change permissions:
```bash
chmod +x myscript.sh        # make executable for everyone
chmod 755 myscript.sh       # owner=rwx, group=rx, others=rx
chmod 600 secrets.txt       # owner=rw, others=nothing
sudo chown user:group file  # change ownership
```

For our project, the daemon will run as **root** to access USB devices, so file permissions matter for security.

---

## 8. Text Editors

You'll need to edit config files. Two main options on Rocky:

### nano (easy — recommended for beginners)

```bash
nano myfile.txt
```

- Type your text. Use arrow keys to move.
- `Ctrl+O` → save (then Enter to confirm filename)
- `Ctrl+X` → exit
- `Ctrl+K` → cut a line, `Ctrl+U` → paste
- Help is shown at the bottom of the screen.

### vim (powerful — what real Linux admins use)

```bash
vim myfile.txt
```

- Two modes: **Command mode** (default) and **Insert mode**
- Press `i` to enter Insert mode (now you can type)
- Press `Esc` to go back to Command mode
- In Command mode: `:w` save, `:q` quit, `:wq` save+quit, `:q!` force quit without saving
- I'd start with nano for now. Learn vim later — it's worth it long-term.

---

## 9. Services (systemd)

Linux runs background services using **systemd**. Our USB defense daemon will be a systemd service, so this matters.

```bash
sudo systemctl start usbguard      # start a service
sudo systemctl stop usbguard       # stop it
sudo systemctl restart usbguard    # restart
sudo systemctl status usbguard     # check if running + recent logs
sudo systemctl enable usbguard     # auto-start at boot
sudo systemctl disable usbguard    # don't auto-start
journalctl -u usbguard             # see all logs for a service
journalctl -u usbguard -f          # follow logs live
```

---

## 10. Networking Basics

```bash
ip addr               # show network interfaces and IPs (replaces "ifconfig")
ping google.com       # test connectivity
ss -tlnp              # show listening ports (replaces "netstat")
curl https://example.com     # download a URL
wget https://example.com/file.iso   # download a file
```

---

## 11. USB-Specific Commands (you'll use these a lot!)

```bash
lsusb                       # list all USB devices currently connected
lsusb -v                    # verbose — shows VID, PID, descriptors
lsblk                       # list block devices (USB drives appear here)
udevadm monitor --udev      # watch USB events live as you plug/unplug
udevadm info /dev/sdb       # full info about a connected USB drive
dmesg | tail -20            # kernel messages (USB inserts log here)
```

When you plug in a USB stick, watch what happens with:
```bash
sudo dmesg -w
```
(Press Ctrl+C to stop watching.)

---

## 12. Pipes and Redirection

The pipe `|` sends one command's output into another command's input. Powerful.

```bash
ls -l | grep ".py"               # list files, filter for .py
cat /var/log/messages | tail -20 # show last 20 lines of log
ps aux | grep python             # find python processes
```

Redirect output to a file:
```bash
ls > files.txt          # save output (overwrite)
ls >> files.txt         # append
echo "hello" > a.txt    # write "hello" to a.txt
```

---

## 13. Common Beginner Mistakes

1. **Forgetting `sudo`** for system commands → "Permission denied". Just retry with `sudo`.
2. **Running `rm -rf`** — devastating if you point it at the wrong place. ALWAYS double-check the path.
3. **Linux is case-sensitive.** `File.txt` and `file.txt` are different files. Windows isn't case-sensitive — Linux is.
4. **Spaces in paths need quotes:** `cd "My Folder"` not `cd My Folder`.
5. **`Ctrl+C` in terminal** → cancel a running command. Doesn't copy text. To copy, select with mouse + right-click in most terminals.
6. **`Ctrl+Shift+C` and `Ctrl+Shift+V`** in most terminals for copy/paste.

---

## 14. Tab Completion (huge time-saver)

Press **Tab** anywhere on the command line and Linux auto-completes file names, folder names, and command names.

Example: typing `cd Doc` then Tab → autocompletes to `cd Documents/`.

If multiple matches, press Tab twice to see them all.

---

## 15. The History

```bash
history          # see last commands you ran
!42              # re-run command number 42 from history
!!               # re-run the last command
sudo !!          # re-run the last command with sudo (super useful!)
```

Press **Up arrow** to scroll through previous commands.

---

## 16. Getting Help

```bash
man ls                # manual page for ls (press q to quit)
ls --help             # quick help for most commands
tldr ls               # simpler examples-based help (need to install: dnf install tldr)
```

---

## 17. Quick Cheat Sheet for THIS Project

You'll mostly use these commands while building the USB defense system:

```bash
# Check connected USB
lsusb

# Watch live USB events
sudo udevadm monitor --udev

# Edit config files
sudo nano /etc/usbguard/usbguard-daemon.conf

# Start/stop the defense daemon
sudo systemctl start usb-defense
sudo systemctl status usb-defense

# View logs
sudo journalctl -u usb-defense -f

# Run the GUI (after building it)
python3 ~/USB-Defense/src/main.py

# Install something we need
sudo dnf install <package-name>
```

---

## 18. What to Read Next

After Rocky Linux is installed, try these to practice:

1. Open terminal, run: `pwd`, `ls`, `cd /`, `ls`, `cd ~`, `ls -la`
2. Make a folder: `mkdir test`, then `cd test`, then `touch hello.txt`
3. Edit it: `nano hello.txt`, type something, save (Ctrl+O, Enter, Ctrl+X)
4. View it: `cat hello.txt`
5. Delete it: `rm hello.txt`, then `cd ..`, then `rmdir test`

Do this 5-10 times — muscle memory matters more than memorization.

---

That's enough to start. We'll learn deeper Linux skills as the project demands them.
