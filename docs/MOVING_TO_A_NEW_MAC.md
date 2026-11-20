# Moving the assistant to a new Mac

You need a USB drive: 32 GB or more, formatted exFAT or APFS (not FAT32).

## On the old Mac

1. Plug in the drive. `ls /Volumes` shows its name.
2. In Terminal:
    ```bash
    cd ~/code/home_assistant_live
    scripts/export_to_new_mac.sh /Volumes/<drive>
    ```
3. Wait for `==> done`. The old Mac's services and VM are now off. Leave them off.
4. Eject the drive.

## On the new Mac

1. Finish the macOS setup wizard and join Wi-Fi.
2. System Settings → Wi-Fi → Details → Private Wi-Fi address: **Fixed** (or Off).
3. Plug in the drive.
4. In Terminal:
    ```bash
    bash /Volumes/<drive>/studio-assistant-move/bootstrap_mac.sh
    ```
5. Stay for the first few minutes and answer:
    - Xcode tools dialog → **Install**, then run step 4 again.
    - Your Mac password, a few times.
    - Docker → **Accept**.
    - "Terminal wants to control…" or "…access data from other apps" → **Allow**.
6. At `nothing below needs you`, walk away. The model download can take an hour.
7. Wait for `smoke: pass` and `==> done`.

## After

1. Router (`https://192.168.1.1`): reserve the address and hardware address the script printed.
2. Say "Hey Jarvis" to the speaker.
3. Open `http://<name>.local:8775` from the laptop (the script prints the name).
4. Erase the drive. It still holds a copy of Home Assistant.

## If it stops

1. Do what the last message says.
2. Run step 4 again. It skips what is already done.

Remote Login and SSH are not needed at any point.
