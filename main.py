from curl_cffi import requests
from scrapy import Selector
from fastapi import FastAPI, Request
from datetime import datetime, timedelta
from urllib.parse import quote
import logging
import html
import json
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI()

LOGIN_URL = "https://partner.elliemd.com/MemberToolsDotNet/Login/FirestormLogin.aspx?ReferringDealerID=1032328"


def get_yesterday(days=1):
    return (datetime.now() - timedelta(days=days)).date()

def get_date_days_ago(days=7):
    days_list = []
    for day in range(1, days + 1):
        days_list.append((datetime.now() - timedelta(days=day)).date())
    return days_list


async def login(username: str, password: str, session: requests.AsyncSession):
    r = await session.get(LOGIN_URL)
    if r.status_code != 200:
        return {"status": False, "error": f"Failed to load login page"}

    sel = Selector(text=r.text)
    viewstate = sel.xpath('//*[@name="__VIEWSTATE"]/@value').get()
    eventvalidation = sel.xpath('//*[@name="__EVENTVALIDATION"]/@value').get()

    if not viewstate or not eventvalidation:
        return {"status": False, "error": "Missing verification tokens"}

    data = f"__LASTFOCUS=&__EVENTTARGET=&__EVENTARGUMENT=&__VIEWSTATE={quote(viewstate, safe='')}&__VIEWSTATEGENERATOR=1279CEE1&__EVENTVALIDATION={quote(eventvalidation, safe='')}&txtLostEmailAddress=&txtRPDealerURL=&txtRPDealerID=&txtDealerID={quote(username, safe='')}&Password={quote(password, safe='')}&cboCountry=USA&btnLogin=Login"

    headers = {
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": "Mozilla/5.0"
    }

    r = await session.post(LOGIN_URL, data=data, headers=headers)

    if "Invalid login" in r.text:
        return {"status": False, "error": "Invalid credentials"}

    return {"status": True}


def extract_reports(raw_html: str, days=None):
    if not days:
        days = [get_yesterday()]
    else:
        days = get_date_days_ago(days)
        
    sel = Selector(text=raw_html)

    rows = sel.css(".TGMainTable tr")
    if not rows:
        return []

    reports = []
    for row in rows[1:]:
        entry_str = row.xpath('./td[13]/text()').get('')
        entry_date = datetime.strptime(entry_str, "%m/%d/%Y").date()

        if entry_date in days:
            reports.append({
                "Level": row.xpath('./td[1]/text()').get(''),
                "Bus. Phone": row.xpath('./td[4]/text()').get('').replace("+", ""),
                "ID": row.xpath('./td[5]/text()').get(''),
                "First Name": row.xpath('./td[6]/text()').get('').split(",")[1].strip() if "," in row.xpath('./td[6]/text()').get('') else "",
                "Last Name": row.xpath('./td[6]/text()').get('').split(",")[0].strip(),
                "Email": row.xpath('./td[8]/a/@href').get('').split(":")[1] if row.xpath('./td[8]/a/@href').get('') else "",
            })

    return reports


async def get_reports(session: requests.AsyncSession, days=1):
    GENEALOGY_URL = "https://partner.elliemd.com/MemberToolsDotNet/Reports/TabularGenealogy.aspx"
    res = await session.get(GENEALOGY_URL)
    sel = Selector(text=res.text)
    viewstate = sel.xpath('//*[@name="__VIEWSTATE"]/@value').get()
    eventvalidation = sel.xpath('//*[@name="__EVENTVALIDATION"]/@value').get()

    headers = {
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "user-agent": "Mozilla/5.0",
    }

    payload = f"Timeout_CountryID=USA&ReportCode=&ctl00_RadScriptManager1_TSM=%3B%3BSystem.Web.Extensions%2C+Version%3D4.0.0.0%2C+Culture%3Dneutral%2C+PublicKeyToken%3D31bf3856ad364e35%3Aen-US%3Aa8328cc8-0a99-4e41-8fe3-b58afac64e45%3Aea597d4b%3Ab25378d2%3BTelerik.Web.UI%2C+Version%3D2024.1.131.45%2C+Culture%3Dneutral%2C+PublicKeyToken%3D121fae78165ba3d4%3Aen-US%3A9948a144-ff46-44f4-9ae0-6f54d8eaff7b%3A16e4e7cd%3Aed16cbdc%3A4877f69a%3A33715776%3A86526ba7%3A874f8ea2&__EVENTTARGET=ctl00%24MainContent%24Sort_Enrolled_ASC&__EVENTARGUMENT=&__LASTFOCUS=&__VIEWSTATE={quote(viewstate, safe='')}&__VIEWSTATEGENERATOR=2190795F&__SCROLLPOSITIONX=628&__SCROLLPOSITIONY=100&__EVENTVALIDATION={quote(eventvalidation, safe='')}&ctl00_RadFormDecorator1_ClientState=&ctl00%24MainContent%24cboSearchList=Bus.+Phone&ctl00%24MainContent%24txtSearchValue=&ctl00%24MainContent%24cboDealershipNumber=789153"

    res = await session.post(GENEALOGY_URL, headers=headers, data=payload)

    if res.status_code != 200:
        return {"status": False, "error": f"Fetch failed {res.status_code}"}
    
    return {"status": True, "reports": extract_reports(res.text, days=days)}

@app.post("/team")
async def fetch_reports(request: Request):
    # print(request)
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    days = body.get("days", 1)
    async with requests.AsyncSession(timeout=200, impersonate="chrome120") as session:
        try:
            logged = await login(username, password, session)
            if not logged["status"]:
                return {"error": logged["error"]}

            result = await get_reports(session, days=days)
            if not result["status"]:
                return {"error": result["error"]}

            return {
                "total": len(result["reports"]),
                "reports": result["reports"]
            }

        except Exception as e:
            logging.exception("Error while fetching reports")
            return {"error": str(e)}
        
        
@app.get("/")
def root():
    return {"message": "EllieMD API is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
    
    
# curl -X POST "http://127.0.0.1:8000/team" ^
#   -d "{\"username\":\"restoremyhealthtoday@gmail.com\",\"password\":\"Hoover1979!\",\"days\":5}"