# Data to Physical
Put real digital data on paper with version 40 QR codes. Can encode into PDF and decode from PDF with a python script.
``` shell
# Update packages, install python3 and extra requirements
sudo apt update
sudo apt install python3 python3-reportlab python3-qrcode python3-pyzbar -y
pip install pdf2image --break-system-packages

# To clone the script from github to your linux computer.
curl -O https://raw.githubusercontent.com/Niam3231/data-to-paper/refs/heads/main/store-paper.py

# This will start the script and give you the useage:
chmod +x ./store-paper.py && python3 ./store-paper.py -h
```
