# Team: qwerty 

##  Problem Statement: FMCG 
**Using AI to speed up and scale RFP responses for faster B2B growth.** 

Manual RFP response limits revenue growth and is highly inefficient. Currently, manual portal scanning misses up to 50% of winnable RFPs.Technical matching takes 3-5 days, as engineers manually compare SKUs against extensive documents.This limits annual capacity to 20 RFPs, resulting in 2-3 crore in lost revenue.Furthermore, 35% of submissions use suboptimal matches, which reduces win rates. 

##  The Solution: Agentic AI System
Our approach focuses on intelligent RFP automation, turning a 7-day process into 2 hours. We built a Faceless AI Agent System for 24/7 RFP processing.

### Multi-Agent Architecture
Our system utilizes LangGraph to build multi-step AI workflows using specialized agents:

* **Master Agent:** Selects the best RFP and finds the tender with the maximum score. It returns RFP details, matched products, total price, and the final score. 
* **Sales Agent:** Auto-scans 20 URLs daily. It scrapes the website by calling a custom-made API, filters tenders whose deadline is within the next 3 months, and uses a scoring formula to find the best RFP to return to the Master Agent. 
* **Technical Agent:** Extracts specs in 10 mins. An intelligent SKU Matching & Product Recommendation Engine scans RFP/Tender documents and OEM product data. It compares specs, calculates the match percentage, and identifies the top 5 products per tender item. Output includes Matched SKUs, Match Score, Ranking, and Status. 
* **Pricing Agent:** Generates a quote in 30 mins. After getting a list of OEM products from technical and verifying with the RFP description given by master, it generates an estimated price for each matched product list. It then calculates the total estimate cost of the tender. 

## RFP Scoring System & Methodology
Our weighted scoring algorithm evaluates RFPs based on the following criteria:

* **Technical Match:** 35% (Core competency alignment)
* **Price Competitiveness:** 25% (Cost optimization) 
* **Delivery Capability:** 15% (Timeline feasibility) 
* **Compliance & Certification:** 15% (Quality assurance) 
* **Risk Assessment:** 10% (Delivery risk mitigation) 

## Business Impact & ROI
The system allows for rapid scaling to paints, tiles, and adhesives RFPs simply by uploading new product catalogs, with no code changes required. 

* **Response Time:** Reduced from 7 days to 2 hours (96% faster). 
* **Annual Capacity:** Increased from 20 RFPs to 100+ RFPs (5x increase). 
* **Win Rate:** Improved from 25% to 35-40% (+40% improvement). 

##  Tech Stack
* **Agent Framework:** LangGraph - orchestration, Google Generative AI - Gemini integration. 
* **Backend Framework:** Flask 3.0 - Python web framework, Flask-CORS - Cross-origin support, Werkzeug - WSGI utilities, python-dotenv - Environment variables. 
* **Web & Data Collection:** Puppeteer - Web scraping, Requests - HTTP client. 
* **Document Handling:** PyPDF2 - PDF manipulation, ReportLab - PDF generation. 
* **Data Processing:** Pandas - Data manipulation, openpyxl - Excel operations, Tabulate - Formatted output. 

##  Team qwerty (VJTI) 
* **Piyush Patil** 
* **Ojas Patil** 
* **Yash Ogale**
* **Harsh Ogale** 
* **Atharva Purushe** 


##  Important Links 

* **Main Website:** https://ey-techathon-qwerty.onrender.com
* **Video Demo:** https://drive.google.com/file/d/1nN1OYZGEJrNBvS62Cpx8nf_PWhLfnVYA/view?usp=sharing 
* **Backend GitHub:** https://github.com/harshoqale04/EY_TECHATHON_qwerty 
* **Frontend GitHub:** https://github.com/Ojasp21/tender 
* **Live Website:** https://tender-frontend-eight.vercel.app/ 
* **Project Report:** https://docs.google.com/document/d/1wr09wCHdpsAb94ujXcSMIbwkPCGWolzxz20ejbxWwll/edit?usp=sharing 
