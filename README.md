# 🌐 Social Media Downloader

A simple, fast, and user-friendly **local web application** for downloading publicly available videos and images from supported social media platforms.

Built with **Python, Flask, HTML, CSS, JavaScript, and yt-dlp**, the application provides a clean interface for saving public media directly to your device.

## ✨ Features

* 📥 Download publicly available **videos and images**
* 🌐 Supports **multiple social media platforms**
* 🎥 Download videos in available formats/qualities
* 🖼️ Download images from supported platforms
* 🔒 **Private accounts and private content are restricted**
* 🚫 Does not bypass authentication or privacy controls
* 🖥️ Runs completely on your local machine
* ⚡ Fast and lightweight interface
* 📱 Responsive web UI
* 🚀 Easy Windows startup with `start.bat`
* 📦 Automatic dependency installation

## 🛠️ Tech Stack

* **Python**
* **Flask**
* **HTML5**
* **CSS3**
* **JavaScript**
* **yt-dlp**

## 📂 Project Structure

```text
social-media-downloader/
│
├── app.py
├── index.html
├── requirements.txt
├── start.bat
├── start.sh
└── README.md
```

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/social-media-downloader.git
cd social-media-downloader
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv
```

### 3. Activate the Virtual Environment

**Windows:**

```bash
.venv\Scripts\activate
```

**Linux / macOS:**

```bash
source .venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Start the Application

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:8765
```

## 🪟 Windows Quick Start

Windows users can simply double-click:

```text
start.bat
```

The script will:

1. Create the virtual environment if it doesn't exist
2. Activate the environment
3. Install the required dependencies
4. Start the application

## 🔐 Privacy & Security

This project is designed to work with **publicly accessible content only**.

It does **not**:

* ❌ Access private accounts
* ❌ Bypass login requirements
* ❌ Circumvent privacy settings
* ❌ Attempt to access restricted content

Private-account content and other protected media are intentionally restricted.

## ⚠️ Disclaimer

This project is intended for **personal and educational use**.

Only download media that you have permission to download. Respect the copyright, privacy, and terms of service of the respective platforms and content creators.

The developers are not responsible for misuse of this application.

## 🤝 Contributing

Contributions, suggestions, and improvements are welcome.

1. Fork the repository
2. Create a new branch
3. Make your changes
4. Commit your changes
5. Open a Pull Request

## ⭐ Support

If you find this project useful, consider giving the repository a ⭐ on GitHub!


