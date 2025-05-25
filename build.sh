#!/usr/bin/env bash
# exit on error
set -o errexit

# Инсталиране на Chrome
apt-get update
apt-get install -y wget gnupg
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list
apt-get update
apt-get install -y google-chrome-stable

# Инсталиране на Python зависимости
pip install -r requirements.txt 