from re import M, search
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup as soup
from urllib.request import urlopen as uReq
import requests
from googleapiclient.discovery import build
from datetime import datetime
import time
from datetime import timedelta

my_api_key = "AIzaSyA2f9UY1eL6ljlQ-ZlBe0808_MmtWptizo" #The API_KEY you acquired
my_cse_id = "906dcdf4228b54135" #The search-engine-ID you created

def google_search(search_term, exact_terms, api_key, cse_id, **kwargs):
	query = search_term
	service = build("customsearch", "v1", developerKey=api_key)
	res = service.cse().list(q=query, exactTerms=exact_terms, cx=cse_id, sort="date:r:20220822:20220828", **kwargs).execute()
	if len(res) < 6:
		return []
	else:
		return res['items']

df = pd.read_csv('schedule.csv')
fnames = df["First Name"]
lnames = df["Last Name"]
hs = df["High School"]
links = df["Max Preps Link"]
games = df["Week 12 Game"]
idx = 0

for link in links:

	line = ""
	has = []
	gameopp = games[idx]
	if not pd.isna(gameopp):
		
		
		gameopp = gameopp.replace("@ ", "")
		gameopp = gameopp.replace("vs ", "")
		gameopp = gameopp.replace("(Scrimmage)", "")

		if "schedule" not in link:
			if "football"not in link:
				uClient = uReq(link)
				page_html = uClient.read()
				uClient.close()
				page_soup = soup(page_html, "html.parser")


				teampage = page_soup.find("div", {"class":"athlete-name-school-name"})
				teampage = teampage.div.a["href"]
				teampage = teampage + "football/schedule/"
			else:
				teampage = link + "schedule/"
		else:
			teampage = link
		uClient = uReq(teampage)
		page_html = uClient.read()
		uClient.close()
		page_soup = soup(page_html, "html.parser")
		tables = page_soup.findAll("tbody")
		for table in tables:
			rows = table.findAll("tr")
			for row in rows:
				
				data = row.findAll("td")
				tba = data[2].span
				container = tba.findAll("a")
				if len(container) > 0:
					rowopp = data[2].span.a.text
					rowdate = data[0].div.text[5:]
					month = rowdate.split("/")[0]
					if len(rowdate.split("/")) < 2:
						dt_obj = datetime.strptime("07/15", "%m/%d")
					else:
						day = rowdate.split("/")[1]

						if int(month) < 10:
							month = "0" + month
						if int(day) < 10:
							day = "0" + day
						rowdate = month + "/" + day
						dt_obj = datetime.strptime(rowdate, "%m/%d")
					dt_min = datetime.strptime("11/08", "%m/%d")
					dt_max = datetime.strptime("11/15", "%m/%d")

					if rowopp == gameopp or (dt_obj > dt_min and dt_obj < dt_max):
						container = data[3].findAll("a")
						if len(container) > 0:
							score = data[3].a.text
							if "L" in score:
								if "OT" in score:
									score = score.replace("(OT)", "")
									score = score.replace("L", "")

									score += "(OTL)"
								else:
									score = score.replace("L", "")
									score += " (L)"	
							elif "W" in score:
								if "OT" in score:
									score = score.replace("(OT)", "")
									score = score.replace("W", "")
									score += "(OTW)"
								else:
									score = score.replace("W", "")
									score += " (W)"	
							elif "Preview" in score:
								score = ""
							else:
								score = score.replace("T", "")
								score += " (T)"
							
																					
							line += score


		meem = ";"
		if len(line) < 2:
			st = gameopp + " vs " + hs[idx]
			et = gameopp + " " + hs[idx]
			results = google_search(st, et, my_api_key, my_cse_id, num=10)
			
			for result in results:
				meem+='\"'
				meem += result["title"]
				meem += " ("
				meem += result["link"]
				meem += ")"
				meem+='\";'

		meem = ""
		
		print(fnames[idx], ";", lnames[idx], ";", games[idx], ";", line, meem)
		idx += 1
	else:

		print(fnames[idx], ";", lnames[idx], ";No game")
		idx += 1



