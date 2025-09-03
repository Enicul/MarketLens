### [ Practice Module ] Project Submission Template: Github Repository & Zip File

**[ Naming Convention ]** CourseCode-StartDate-BatchCode-TeamName-ProjectName.zip  

* **[ MTech Thru-Train Group Project Naming Example ]** IRS-PM-2020-01-18-IS02PT-GRP-TeamName-ProjectName.zip  
* **[ MTech Stackable Group Project Naming Example ]** IRS-PM-2020-01-18-STK02-GRP-TeamName-ProjectName.zip  

[Online editor for this README.md markdown file](https://pandao.github.io/editor.md/en.html "pandao")

---

### <<<<<<<<<<<<<<<<<<<< Start of Template >>>>>>>>>>>>>>>>>>>>

---

## SECTION 1 : PROJECT TITLE
## [ Insert Project Title Here ]

<img src="SystemCode/clips/static/project-logo.png"
     style="float: left; margin-right: 0px;" />

---

## SECTION 2 : EXECUTIVE SUMMARY / PAPER ABSTRACT
[Provide background of the problem, why it matters, target users, and the gap you aim to fill.]  

[Summarize the objectives and scope of the project.]  

[Briefly describe the methods, tools, and technologies applied.]  

[Highlight expected results, contributions, and potential impact.]  

---

## SECTION 3 : CREDITS / PROJECT CONTRIBUTION

| Official Full Name  | Student ID (MTech Applicable)  | Work Items (Who Did What) | Email (Optional) |
| :------------------ |:-----------------------------:| :-------------------------| :--------------- |
| Member 1 | A1234567A | xxxxxxxxxx yyyyyyyyyy zzzzzzzzzz | email@domain.com |
| Member 2 | A1234567B | xxxxxxxxxx yyyyyyyyyy zzzzzzzzzz | email@domain.com |
| Member 3 | A1234567C | xxxxxxxxxx yyyyyyyyyy zzzzzzzzzz | email@domain.com |
| Member 4 | A1234567D | xxxxxxxxxx yyyyyyyyyy zzzzzzzzzz | email@domain.com |

---

## SECTION 4 : VIDEO OF SYSTEM MODELLING & USE CASE DEMO

[![Demo Video](http://img.youtube.com/vi/VIDEO_ID/0.jpg)](https://youtu.be/VIDEO_ID "Demo Video")

Note: It is not mandatory for every project member to appear in the video presentation; presentation by one member is acceptable.  
More reference video presentations [here](https://telescopeuser.wordpress.com/2018/03/31/master-of-technology-solution-know-how-video-index-2/ "video presentations")

---

## SECTION 5 : USER GUIDE

`Refer to appendix <Installation & User Guide> in project report at Github Folder: ProjectReport`

### [ 1 ] To run the system using iss-vm

> download pre-built virtual machine from http://bit.ly/iss-vm  
> start iss-vm  
> open terminal in iss-vm  

```bash
$ git clone https://github.com/your-repo/project.git
$ source activate iss-env-py2
(iss-env-py2) $ cd project/SystemCode/clips
(iss-env-py2) $ python app.py
````

> **Go to URL using web browser** [http://0.0.0.0:5000](http://0.0.0.0:5000) or [http://127.0.0.1:5000](http://127.0.0.1:5000)

### \[ 2 ] To run the system in other/local machine

> Install necessary libraries (Python 2 example shown).

```bash
$ sudo apt-get install python-clips clips build-essential libssl-dev libffi-dev python-dev python-pip
$ pip install pyclips flask flask-socketio eventlet simplejson pandas
```

---

## SECTION 6 : PROJECT REPORT / PAPER

`Refer to project report at Github Folder: ProjectReport`

**Recommended Sections for Project Report / Paper:**

* Executive Summary / Paper Abstract
* Sponsor Company Introduction (if applicable)
* Business Problem Background
* Market Research
* Project Objectives & Success Measurements
* Project Solution (Domain modelling & system design)
* Project Implementation (System development & testing)
* Project Performance & Validation
* Project Conclusions: Findings & Recommendation
* Appendix: Project Proposal
* Appendix: Mapped System Functionalities against modular course knowledge/skills
* Appendix: Installation and User Guide
* Appendix: 1–2 page individual project reflection report per member
* Appendix: List of Abbreviations (if applicable)
* Appendix: References (if applicable)

---

## SECTION 7 : MISCELLANEOUS

`Refer to Github Folder: Miscellaneous`

### Example Files

* `SurveyResults.xlsx` — raw survey data
* Insights derived — used in system modelling

---

### 


