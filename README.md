# 📈 BSE Announcement Scraper & Analyzer

![BSE Scraper Banner](https://img.shields.io/badge/BSE-Announcement%20Scraper-blue?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiNmZmZmZmYiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIiBjbGFzcz0ibHVjaWRlIGx1Y2lkZS10cmVuZGluZy11cCI+PHBvbHlsaW5lIHBvaW50cz0iMjMgNiAyMyAxIDEgMSI+PC9wb2x5bGluZT48cG9seWxpbmUgcG9pbnRzPSIxIDIzIDIzIDIzIDIzIDE2Ij48L3BvbHlsaW5lPjxsaW5lIHgxPSIxIiB5MT0iMTIiIHgyPSI4IiB5Mj0iMTIiPjwvbGluZT48bGluZSB4MT0iMTYiIHkxPSIxMiIgeDI9IjIzIiB5Mj0iMTIiPjwvbGluZT48cGF0aCBkPSJtOCAyMyA0LTEyIDQgMTIiPjwvcGF0aD48cGF0aCBkPSJNMSA2IDggNmw3IDEwIDcgLTEwaDIiPjwvcGF0aD48L3N2Zz4=)
![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)
![LLM: Ollama](https://img.shields.io/badge/LLM-Ollama-green.svg)

A powerful tool to scrape, process, and analyze Bombay Stock Exchange (BSE) company announcements with advanced PDF extraction capabilities and LLM-based information extraction.

## 🚀 Features

- **🕸️ Automated Scraping:** Extract BSE announcements based on date ranges and categories
- **📄 PDF Processing:** Download and process announcement PDFs
- **🔍 Content Extraction:** Extract text, tables, and images from PDFs
- **🖼️ OCR Processing:** Convert images to text for deeper analysis
- **🤖 LLM Analysis:** Leverage Ollama for automated question answering
- **📊 Data Organization:** Structured storage of all extracted information
- **📝 Comprehensive Reports:** Generate detailed summaries and insights

## 🛠️ Installation

Clone this repository and install the required dependencies:

```bash
git clone https://github.com/yourusername/bse-announcement-scraper.git
cd bse-announcement-scraper
pip install -r requirements.txt
```

### 📋 Requirements

- Python 3.8+
- Chrome browser and ChromeDriver
- Tesseract OCR installed on your system
- Ollama for LLM processing

### 🔧 Setting up Tesseract OCR

Make sure to install [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) on your system:

- **Windows:** Download from [here](https://github.com/UB-Mannheim/tesseract/wiki)
- **macOS:** Install via Homebrew: `brew install tesseract`
- **Linux:** Install via apt: `sudo apt install tesseract-ocr`

Update the path in the script to match your Tesseract installation:
```python
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # Windows example
```

### 🤖 Setting up Ollama

1. Install [Ollama](https://ollama.ai/) on your system
2. Pull a model (recommended: `tinyllama`):
```bash
ollama pull tinyllama
```
3. Start the Ollama server:
```bash
ollama serve
```

## 💻 Usage

Run the main script to start the scraping process:

```bash
python scraper.py
```

The script will:
1. Ask for date range (format: DD/MM/YYYY)
2. Ask for company update type
3. Scrape BSE website for matching announcements
4. Download PDF files
5. Extract and process all content
6. Run LLM-based analysis

## 📁 Output Structure

```
BSE_Announcements/
├── DD_MM_YYYY/
│   ├── CompanyName_ScriptID_Description/
│   │   ├── CompanyName_ScriptID_Description.pdf
│   │   ├── metadata.json
│   │   ├── text/
│   │   │   └── extracted_text.txt
│   │   ├── ocr/
│   │   │   └── ocr_text.txt
│   │   ├── tables/
│   │   │   └── table1.csv
│   │   └── images/
│   │       ├── page1_full.png
│   │       └── page1_img1.png
├── QA_Results/
│   ├── all_qa_results.csv
│   ├── qa_summary_table.csv
│   └── DD_MM_YYYY/
│       └── CompanyName_ScriptID_Description/
│           └── qa_results.json
└── merged_announcements_data.json
```

## 🔬 Analyzed Information

The system automatically answers these key questions for each announcement:

1. 🤝 Does the announcement mention a merger or acquisition?
2. 💰 Is there any mention of a stock split or dividend declaration?
3. ⚖️ Are there any regulatory actions or penalties mentioned?
4. 📊 Is there an earnings report included in this announcement?
5. 👨‍💼 Does the announcement include any management changes?

Results are stored in easy-to-analyze JSON and CSV formats.

## 🔄 Customization

You can customize the questions asked by modifying the `PREDEFINED_QUESTIONS` list in `ollama.py`:

```python
PREDEFINED_QUESTIONS = [
    "Does the announcement mention a merger or acquisition?",
    # Add your custom questions here
]
```

## 🔌 Advanced Usage

### Processing Large Date Ranges

For extensive data collection over large date ranges, you can split the process:

```bash
# First batch
python scraper.py  # Enter date range 01/01/2023 to 31/01/2023

# Second batch
python scraper.py  # Enter date range 01/02/2023 to 28/02/2023
```

The tool preserves previously processed announcements to avoid duplicates.

### Using Different LLM Models

You can use different Ollama models by changing the model parameter:

```python
ollama.process_announcements_with_ollama_batch(base_output_dir, announcements_data, model="llama2")
```

## 📚 Technical Details

- **Web Scraping:** Uses Selenium for dynamic content extraction
- **PDF Processing:** Leverages PyMuPDF with fallbacks to tabula-py
- **OCR Pipeline:** OpenCV preprocessing + Tesseract OCR
- **LLM Integration:** REST API calls to Ollama with robust retry mechanisms
- **Data Storage:** JSON and CSV for maximum compatibility

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📧 Contact

For questions and feedback, open an issue or contact:  
[your-email@example.com](mailto:your-email@example.com)

---

⭐ Star this repo if you find it useful!
