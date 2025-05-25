#!/usr/bin/env bash
# exit on error
set -o errexit

# Инсталиране на Chrome
apt-get update
apt-get install -y wget gnupg2 unzip
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list
apt-get update
apt-get install -y google-chrome-stable

# Инсталиране на ChromeDriver
CHROME_VERSION=$(google-chrome --version | awk '{print $3}' | cut -d'.' -f1)
wget -q "https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip"
unzip chromedriver_linux64.zip
mv chromedriver /usr/local/bin/
chmod +x /usr/local/bin/chromedriver

# Инсталиране на Python зависимости
pip install --no-cache-dir -r requirements.txt 