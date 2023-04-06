import json
import os
import shutil
import glob
import timeit
import pytz
import re
from build_graph import *
from report import *
from pdfutil import *
from PyPDF2 import PdfFileWriter
from PyPDF2 import PdfFileReader
from datetime import datetime, timedelta
import linecache
import tracemalloc
import psutil

'''
This file contains a function for building the database query as well as the main code to make the necessary queries. 
The script creates pdfs for each region of the United States, in a folder called "results" located in the working directory. 

'''

'''
buildQuery is the function that builds a query by taking the desired verification type, date range, NDFD issuance, element, sources and their
corresponding offsets, and Weather Forecast Office. It returns a string that contains the query, which does not have console output, but saves
the SQL return as a json in the format "tmp/{verification type}_{element}_{NDFD issuance}_{WFO}.json" in the working directory. At the end
of the script the "tmp" folder and all its contents are deleted.
'''
def buildMonthlyQuery(verifType, date, issuance, element, sources, offsets, wfo, metrics): 

	query = '''psql -t -h 205.156.8.76 -d verification -p 5432 -U verif_web -c "SELECT sql_tojson_format('SELECT source, mask, dataStr,stats_key, cycle, json_agg(json_build_object(proj, json_build_object(''ThresholdValues'', stats_value, ''total_cases'',total_cases, ''total_cnt_count'', total_cnt_counts, ''cnt_count'', cnt_counts, ''ndfd_proj'',ndfd_proj))) as value FROM (SELECT source, mask, proj, ndfd_proj,stats_key, cycle,dataStr, array_agg(cnt_counts) as cnt_counts, array_agg(total_cnt_count) as total_cnt_counts, array_agg(stat_cnt/total_cnt_count) as stats_value, max(total_cases) as total_cases FROM ( SELECT source, mask, proj, ndfd_proj,stats_key, cycle, nr, dataStr, cnt_counts, sum(total_cases) as total_cases, sum(stat_cnt) as stat_cnt, sum(cnt) as total_cnt_count FROM ( SELECT source, dayRef, mask, stats_key, cycle, proj, ndfd_proj, nr, dataStr, total_cases, stat*cnt as stat_cnt, CASE WHEN stat is not null THEN cnt ELSE null END as cnt, last_value(cnt) OVER (ORDER BY nr,source, mask, stats_key, cycle, proj, ndfd_proj) as cnt_counts FROM ( SELECT source, mask, dayRef,stats_key, cycle, proj, ndfd_proj, a.nr as nr, dataStr, total_cases::float, cnt_count::float as cnt, stats::float as stat FROM (SELECT * FROM ('''
	for metric in metrics:
		offsets_iter = iter(offsets)
		# Temporary handling for missing data
		if verifType == "NDFD":
			sample = "V"
		else:
			sample = "I"

		if metric == "BRIER":
			brier_array = "Array[BRIER]"
		else:
			brier_array = metric

		query += f'''SELECT source, mask, ''data'' as dataStr, ''cycle_''|| cycle||''Z'' as cycle,lower(''{metric}'') as stats_key, ndfd_proj as ndfd_proj, ''proj_''|| proj as proj, {metric} as stats_value, total_cases, cnt_counts, date as dayRef FROM (SELECT source,mask,LPAD(cycle::text,2,''0'') as cycle,date, proj, ndfd_proj,'''
		for metric_inner in metrics:
			query += metric_inner + ","
		query += f'''cnt_counts,total_cases,yncontingency FROM ndfd_stats.ndfd_stat WHERE element=''{element}'' AND ndfd_proj>0 AND sample_type = ''{sample}'' AND fcst_type=''G'' AND verif_type=''{verif_type[0]}'' AND ('''
		for source in sources:
			if verifType == "NDFD":
				query += f''' ( ( (cycle = ''{issuance}'' AND date IN(''{date}''))) AND source = ''{source}'' AND mask IN(''{wfo}''))'''
			else:
				query += f''' ( ( (cycle = ''{next(offsets_iter)}'' AND date IN(''{date}''))) AND source = ''{source}'' AND mask IN(''{wfo}''))'''
			if source == sources[-1]:
				query += ")) tt "
			else:
				query += " OR"
		if metric == metrics[-1]:
			query += ") t0 "
		else:
			query += "UNION "
	query += f'''ORDER BY source, mask, stats_key,dayRef,cycle, proj, ndfd_proj) t, unnest(t.stats_value, t.cnt_counts) WITH ORDINALITY a(stats, cnt_count, nr) ORDER BY nr,source, mask, stats_key, cycle, proj, ndfd_proj, dayRef ) foo ORDER BY source, dayRef, mask, cycle, proj, ndfd_proj, nr )fo GROUP BY 1,2,3,4,5,6,7,8,9 ORDER BY 1,2,3,4,5,6,7,8,9 )f WHERE total_cnt_count>0 GROUP BY 1,2,3,4,5,6,7 ORDER BY 1,2,3,4,5,6,7) proj_obj group by 1,2,3,4,5 ORDER BY 1,2,3,4,5');" > tmp/{verif_type}_{element}_{str(issuance)}_{wfo}.json'''

	return query


def buildDailyQuery(verifType, dateStart, dateEnd, issuance, element, sources, offsets, wfo, metrics): 

	query = '''psql -t -h 205.156.8.76 -d verification -p 5432 -U verif_web -c "SELECT sql_tojson_format_hier('SELECT source, mask, dataStr, cycle, stats_key, hier,json_agg(json_build_object(proj, json_build_object(''ThresholdValues'', stats_value, ''total_cases'', total_cases, ''total_cnt_count'', total_cnt_counts, ''cnt_count'', cnt_counts, ''ndfd_proj'',ndfd_proj, ''hier'',hier))) as value FROM (SELECT source, mask, proj, ndfd_proj, cycle,stats_key, hier, dataStr, array_agg(cnt_counts) as cnt_counts, array_agg(total_cnt_count) as total_cnt_counts, array_agg(stat_cnt/total_cnt_count) as stats_value, max(total_cases) as total_cases FROM ( SELECT source, mask, proj, ndfd_proj, cycle, stats_key, hier, dataStr, nr, cnt_counts, sum(total_cases) as total_cases, sum(stat_cnt) as stat_cnt, sum(cnt) as total_cnt_count FROM ( SELECT source, dayRef, mask, cycle, proj, ndfd_proj, stats_key, dataStr, hier, nr, total_cases, stat*cnt as stat_cnt, cnt, last_value(cnt) OVER (ORDER BY nr,source, mask, cycle, proj) as cnt_counts FROM ( SELECT source, mask, dayRef, cycle, proj, ndfd_proj,stats_key, dataStr, hier, a.nr as nr, total_cases::float, a.cnt_count as cnt, a.stats as stat FROM (SELECT * FROM ('''
	nullcat = "UNION SELECT source, mask, ''data'' as dataStr, null as cycle, null as stats_key, null as proj, null as ndfd_proj, null as stats_value, total_cases, cnt_counts, validtime, issuetime as dayRef, hier FROM ("

	for metric in metrics:
		offsets_iter = iter(offsets)
		if len(metrics) < 3:

			if metric == "BRIER":
				brier_array = "Array[BRIER]"
				getyndim = ""
			else:
				brier_array = metric
				getyndim = "ndfd_stats.get_ynDim1(yncontingency) as "
		else:
			brier_array = metric
			getyndim = ""

		query += f''' SELECT source, mask, ''data'' as dataStr, ''cycle_''||CASE WHEN (substring(issuetime from 12 for 2)=''00'') AND (source = ''BLEND'' OR source = ''BLENDX'') THEN ''01'' WHEN (substring(issuetime from 12 for 2)=''12'') AND (source = ''BLEND'' OR source = ''BLENDX'') THEN ''13'' ELSE substring(issuetime from 12 for 2) END||''Z'' as cycle,lower(''{metric}'') as stats_key, ''proj_''||CASE WHEN substring(issuetime from 12 for 2)=''00'' AND (source = ''BLEND'' OR source = ''BLENDX'') THEN proj-1 WHEN substring(issuetime from 12 for 2)=''12'' AND (source = ''BLEND'' OR source = ''BLENDX'') THEN proj-1 ELSE proj END as proj, ndfd_proj as ndfd_proj, {brier_array} as stats_value, total_cases, {getyndim}cnt_counts, validtime,issuetime as dayRef, hier FROM (SELECT source, mask,issuetime,validtime,proj,ndfd_proj,'''
		for metric_inner in metrics:
			query += metric_inner + ","
		query += '''cnt_counts,total_cases, yncontingency, ''0'' as hier FROM (SELECT source, mask,issuetime,validtime,proj,ndfd_proj,'''
		for metric_inner in metrics:
			query += metric_inner + ","
		query += '''cnt_counts,total_cases, yncontingency, hier FROM ndfd_stats.ndfd_element WHERE'''
		i = 1
		for source in sources:
			if "NDFD" not in source:
				ds_object = datetime.strptime(dateStart, "%Y-%m-%d")
				de_object = datetime.strptime(dateEnd, "%Y-%m-%d")
				yesterday_start = (ds_object - timedelta(days = 1))
				yesterday_end = (de_object - timedelta(days = 1))
				offset = next(offsets_iter)
				if "BLEND" == source or "BLENDX" == source:
					if offset == "12":
						offset = "13"
					if offset == "00":
						offset = "01"
				if int(offset) <= int(issuance):
					hour_offset = int(offset) + 24
					yesterday_start = (yesterday_start + timedelta(hours = hour_offset)).strftime('%Y-%m-%dT%H:00:00')
					yesterday_end = (yesterday_end + timedelta(hours = hour_offset)).strftime('%Y-%m-%dT%H:00:00')
				else:
					yesterday_start = (yesterday_start + timedelta(hours = int(offset))).strftime('%Y-%m-%dT%H:00:00')
					yesterday_end = (yesterday_end + timedelta(hours = int(offset))).strftime('%Y-%m-%dT%H:00:00')
				query += f''' issuetime BETWEEN ''{yesterday_start}'' AND ''{yesterday_end}'' AND source = ''{source}'' AND mask IN(''{wfo}'') AND element=''{element.lower()}'' AND issueTime LIKE ''%T{offset}%'' AND verif_type=''{verifType[0]}'' and hier in (''N'') and lw=''L'')hiertemp'''				
				nullcat += f''' SELECT source, mask,issuetime,validtime,proj,ndfd_proj,{metrics[0]},cnt_counts,total_cases, yncontingency, ''{i-1}'' as hier FROM (SELECT source, mask,issuetime,validtime,proj,ndfd_proj,{metrics[0]},cnt_counts,total_cases, yncontingency, hier FROM ndfd_stats.ndfd_element WHERE issuetime BETWEEN ''{yesterday_start}'' AND ''{yesterday_end}'' AND source = ''{source}'' AND mask IN(''{wfo}'') AND element=''{element.lower()}'' AND issueTime LIKE ''%T{offset}%'' AND verif_type=''{verifType[0]}'' and hier in (''N'') and lw=''L'')hiertemp '''				
			else:
				offset = next(offsets_iter)

				query += f''' issuetime BETWEEN ''{dateStart}T{offset}:00:00'' AND ''{dateEnd}T{offset}:00:00'' AND source = ''NDFD'' AND mask IN(''{wfo}'') AND element=''{element.lower()}'' AND issueTime LIKE ''%T{offset}%'' AND verif_type=''{verifType[0]}'' and hier in (''N'') and lw=''L'')hiertemp'''
				nullcat += f''' SELECT source, mask,issuetime,validtime,proj,ndfd_proj,{metrics[0]},cnt_counts,total_cases, yncontingency, ''{i-1}'' as hier FROM (SELECT source, mask,issuetime,validtime,proj,ndfd_proj,{metrics[0]},cnt_counts,total_cases, yncontingency, hier FROM ndfd_stats.ndfd_element WHERE issuetime BETWEEN ''{dateStart}T{offset}:00:00'' AND ''{dateEnd}T{offset}:00:00'' AND source = ''NDFD'' AND mask IN(''{wfo}'') AND element=''{element.lower()}'' AND issueTime LIKE ''%T{offset}%'' AND verif_type=''{verifType[0]}'' and hier in (''N'') and lw=''L'')hiertemp'''
			if source == sources[-1]:
				query += " ) tt "
				nullcat += ") tt "
			else:
				query += " UNION SELECT source, mask,issuetime,validtime,proj,ndfd_proj,"
				nullcat += " UNION"
				for metric_inner in metrics:
					query += metric_inner + ","
				query += f'''cnt_counts,total_cases, yncontingency, ''{i}'' as hier FROM (SELECT source, mask,issuetime,validtime,proj,ndfd_proj,'''
				for metric_inner in metrics:
					query += metric_inner + ","
				query += "cnt_counts,total_cases, yncontingency, hier FROM ndfd_stats.ndfd_element WHERE"
			i += 1
		if metric == metrics[-1]:
			if len(metrics) < 2:
				query += nullcat
				query += "WHERE 1=2) t0 "
			else:
				query += ") t0 "
		else:
			query += " UNION"

	query += f'''ORDER BY source, mask, stats_key,dayRef,cycle, proj) t, unnest(t.stats_value, t.cnt_counts) WITH ORDINALITY a(stats, cnt_count, nr) ORDER BY nr,source, mask, cycle, proj, dayRef, hier ) foo ORDER BY source, dayRef, mask, cycle, proj, nr )fo GROUP BY 1,2,3,4,5,6,7,8,9,10 ORDER BY 1,2,3,4,5,6,7,8,9,10 )f WHERE total_cnt_count>0 GROUP BY 1,2,3,4,5,6,7,8 ORDER BY 1,2,3,4,5,6,7,8) proj_obj group by 1,2,3,4,5,6 ORDER BY 1,2,3,4,5,6');" > tmp/{verifType}_{element}_{str(issuance)}_{wfo}.json'''

	return query

def display_top(snapshot, key_type='lineno', limit=3):
    snapshot = snapshot.filter_traces((
        tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
        tracemalloc.Filter(False, "<unknown>"),
    ))
    top_stats = snapshot.statistics(key_type)

    print("Top %s lines" % limit)
    for index, stat in enumerate(top_stats[:limit], 1):
        frame = stat.traceback[0]
        # replace "/path/to/module/file.py" with "module/file.py"
        filename = os.sep.join(frame.filename.split(os.sep)[-2:])
        print("#%s: %s:%s: %.1f KiB"
              % (index, filename, frame.lineno, stat.size / 1024))
        line = linecache.getline(frame.filename, frame.lineno).strip()
        if line:
            print('    %s' % line)

    other = top_stats[limit:]
    if other:
        size = sum(stat.size for stat in other)
        print("%s other: %.1f KiB" % (len(other), size / 1024))
    total = sum(stat.size for stat in top_stats)
    print("Total allocated size: %.1f KiB" % (total / 1024))



tracemalloc.start()


# Main script
def main():

	os.nice(1)

	domain_in = input("Enter Domain Code (ex. ER/CONUS): ")


	region_list = domain_in + ".json"


	monthly_in = input("Monthly or Daily? (M/D): ")
	if "M" in monthly_in:
		MONTHLY = True
		DATE = input("Enter Month (YYYY-MM): ")
		DATE = DATE.replace('-', '')
	else:
		MONTHLY = False
		DATE_START = input("Enter Start Date (YYYY-MM-DD): ")
		DATE_END = input("Enter End Date (YYYY-MM-DD): ")

	proj_in = input("Track Missing Projections? (Y/N): ")
	if "Y" in proj_in or "y" in proj_in:
		EXPECTED_PROJ = True
	else:
		EXPECTED_PROJ = False

	thresholds_in = input("All thresholds? (Y/N): ")
	if "Y" in thresholds_in or "y" in thresholds_in:
		ALL_THRESH = True
	else:
		ALL_THRESH = False

	count_in = input("Case Counts? (Y/N): ")
	if "Y" in count_in or "y" in count_in:
		CASE_COUNTS = True
	else:
		CASE_COUNTS = False

	store_in = input("Store data? (Y/N): ")
	if "Y" in store_in or "y" in store_in:
		STORE_DATA = True
	else:
		STORE_DATA = False

	flags = [EXPECTED_PROJ, ALL_THRESH, CASE_COUNTS, STORE_DATA]
	# Opens the cycle adjustments file that is used to set the issuance offsets
	with open("adjustmentObj.json") as json_file:
		ex_elements = json.load(json_file)

	# If there is already a results folder delete it
	if os.path.exists("results"):
		shutil.rmtree("results")


	offsets = list()
	sources = list()
	errors = list()
	proj_txt = list()
	sources_text = list()
	incompleteThresholds = list()
	emptyThresholds = list()
	toc_wfos = dict()

	# Opens list of regions and wfos
	with open(region_list) as wfos_file:
		wfos = json.load(wfos_file)

	if MONTHLY:
		with open("expected_sources.json") as ex_sources_file:
			ex_sources_data = json.load(ex_sources_file)
		with open("expected_proj.json") as ex_elements_file:
			ex_elements = json.load(ex_elements_file)


	else:
		with open("expected_daily_sources.json") as ex_sources_file:
			ex_sources_data = json.load(ex_sources_file)
		with open("expected_daily_proj.json") as ex_elements_file:
			ex_elements = json.load(ex_elements_file)

	# Get the full element name
	with open("elem_codes.json") as elem_codes:
		codes_data = json.load(elem_codes)
		
	with open("adjustmentObj.json") as adjustments_file:
		adjustments_data = json.load(adjustments_file)
	# If there is not already a temporary folder create it
	if not os.path.exists("tmp"):
		os.mkdir("tmp")

	# For every region
	for region in wfos["regions"]:
		TEST = list()
		# Sets the expected vs observed counts of each source for the region to 0

		missingProj = {
			"NDFD": {"expected": 0, "observed": 0},
			"BLEND": {"expected": 0, "observed": 0},
			"BLENDE": {"expected": 0, "observed": 0},
			"GMOS": {"expected": 0, "observed": 0},
			"WPC": {"expected": 0, "observed": 0},
			"URMA": {"expected": 0, "observed": 0},
			"GFS": {"expected": 0, "observed": 0},
			"GLMP": {"expected": 0, "observed": 0},
			"HRRR": {"expected": 0, "observed": 0},
			"HRWA": {"expected": 0, "observed": 0},
			"HRWN": {"expected": 0, "observed": 0},
			"NAM": {"expected": 0, "observed": 0},
			"NAMNEST": {"expected": 0, "observed": 0},
			"NDFD": {"expected": 0, "observed": 0},
			"RAP": {"expected": 0, "observed": 0},
			"SREF": {"expected": 0, "observed": 0},
			"ECMWF": {"expected": 0, "observed": 0},
				}

		# Timer start
		start = timeit.default_timer()

		# Add the region to the email text strings
		errors.append(f"<p style='font-size:22px'><b><u>{region}:</b></u></p>")
			
		# Reset pages to 0 since there is a new pdf for each region
		pages = 0

		print(f"Running {region}:")

		# For every wfo in every region
		for wfo in wfos["regions"][region]:
			wfo_first_page = pages + 1
			TEST.append([1, f"{wfo}: {wfos['regions'][region][wfo]}", wfo_first_page])

			proj_txt.clear()
			sources_text.clear()

			errors.append(f"<p style='font-size:18px'><b>{wfo}: {wfos['regions'][region][wfo]}</b> </p>")
			print(wfo, end="... ", flush=True)
			poi = "- Potential Data Anomaly: "
			# Variable to indicate whether the return had any sources
			hasVtypes = 0
			toc_vtypes = dict()

			# Add the start of the wfo as a bookmark
			toc_wfos.update({wfo:[pages, toc_vtypes]})

			# For every verif type for every wfo in every region
			for verif_type in ex_elements[region]:
				TEST.append([2, verif_type, pages+1])
				# Variable to indicate whether the verif type had any data
				hasElements = 0
				toc_elements = dict()

				# Add the start of the verification type as a bookmark
				toc_vtypes.update({verif_type:[pages, toc_elements]})
				# For every element in every verif type for every wfo in every region
				for element in ex_elements[region][verif_type]:
					missingSources = [source for source in ex_sources_data[region][verif_type][element]]
					longformEl = codes_data["elements"][element.upper()]["name"]
					if "po" in element:
						metrics = ["BRIER"]
					elif "c" in element:
						metrics = ["CSI"]
					elif "vs" in element:
						metrics = ["CSI"]
					else:
						metrics = ["MAE", "ME", "RMSE"]


					# Variable to indicate whether the element had any data
					hasData = 0
					

					# Store the first page of the element
					element_first_page = pages
					incompleteThresholds.clear()
					emptyThresholds.clear()
					issuances = list()
					totalThresholds = dict()

					# Get the expected sources for the element


					# A list of empty thresholds, a list of incomplete thresholds, a list of missing sources, a dictionary with the expected vs observed projections, and a list of text strings with the projections
					missingData = [emptyThresholds, incompleteThresholds, missingSources, missingProj, proj_txt, poi]

					# For every issuance time for every element in every verif type for every wfo in every region
					for issuance in ex_elements[region][verif_type][element]:
						adjustments = adjustments_data[verif_type]["elements"][element]["cycleAdjustObj"][issuance]
						offsets.clear() 
						sources.clear() 
							
						# For every source at every issuance time for every element in every verif type for every wfo in every region
						for source in adjustments_data[verif_type]["elements"][element]["cycleAdjustObj"][issuance]: 

							# Update the list of sources and offsets
							offsets.append(adjustments_data[verif_type]["elements"][element]["cycleAdjustObj"][issuance][source]) 
							sources.append(source) 

						# Build the query and run it on the cmd line
						if MONTHLY:
							os.system(buildMonthlyQuery(verif_type, DATE, issuance, element.lower(), sources, offsets, wfo, metrics))
						else:
							os.system(buildDailyQuery(verif_type, DATE_START, DATE_END, issuance, element.lower(), sources, offsets, wfo, metrics))

						fileName = f"tmp/{verif_type}_{element.lower()}_{str(issuance)}_{wfo}.json"

						# See if pages were added with a call to buildGraph
						tmp = pages

						# Store the returns of the graphing function with missing data and pages
						if MONTHLY:
							returnVals = buildGraph(fileName, element.lower(), issuance, verif_type, DATE, wfo, region, pages, missingData, flags)
						else:
							returnVals = buildGraph(fileName, element.lower(), issuance, verif_type, DATE_START + " - " + DATE_END, wfo, region, pages, missingData, flags)

						pages = returnVals[0]
						missingData = returnVals[1]
						proj_txt = missingData[4]
						poi = missingData[5]
						# If yes, there was data
						if pages > tmp:
							hasData = 1
							hasElements = 1
							hasVtypes = 1
							issuances.append(issuance)
							totalThresholds.update({issuance:returnVals[2]})
					

					if hasData:
						plural = ""
						# Add the start of the verification type as a bookmark
						if CASE_COUNTS:
							metrics.append("Counts")
						toc_elements.update({longformEl:{"stats":metrics, "issuances":issuances, "page":element_first_page, "thresholds":totalThresholds}})
						TEST.append([3, longformEl, element_first_page + 1])
						issuance_first_page = element_first_page + 1
						for toc_issuance in issuances:
							TEST.append([4, toc_issuance, issuance_first_page])
							metric_first_page = 0
							for toc_metric in metrics:
								TEST.append([5, toc_metric, (issuance_first_page + metric_first_page)])
								thresh_first_page = 0
								if len(totalThresholds[toc_issuance]) > 1:
									for toc_threshold in totalThresholds[toc_issuance]:
										TEST.append([6, toc_threshold, (issuance_first_page + metric_first_page + thresh_first_page)])
										thresh_first_page += 1
								metric_first_page += len(totalThresholds[toc_issuance])
							issuance_first_page += metric_first_page

						# Add missing data messages to the array of strings if there are any
						currentError = ""
						if len(missingData[0]) > 0:
							if len(missingData[0]) > 1:
								plural = "s"
							currentError += f"No values in threshold{plural} {[threshold for threshold in missingData[0]]}"
							if len(missingData[1]) > 0:
								if len(missingData[1]) > 1:
									plural = "s"
								currentError += f", less values than expected in threshold{plural} {[threshold for threshold in missingData[1]]}"
							currentError += f" for {verif_type} {longformEl}<br>\n"
						elif len(missingData[1]) > 0:
							if len(missingData[1]) > 1:
									plural = "s"
							currentError += f"Less values than expected in threshold{plural} {[threshold for threshold in missingData[1]]} for {verif_type} {longformEl}<br>\n"
						if len(missingData[2]) > 0:
							if len(missingData[2]) > 1:
									plural = "s"
							sources_text.append(f"- Missing return{plural} for {missingData[2]} from {verif_type} {longformEl}")
				if not hasElements:
					# Delete the verif type from the bookmarks
					del toc_wfos[wfo][1][verif_type]
					del TEST[-1]
			if not hasVtypes:
				# Delete the wfo from the bookmarks
				del toc_wfos[wfo]
				del TEST[-1]
		
			# Merge all the merged pdfs from buildGraph
			merged = sorted(glob.glob(f"results/{region}/{wfo}*merged.pdf"))
			merge(merged, f"results/{region}/{wfo}.pdf", True)

			# Compile summary report
			if len(sources_text) + len(proj_txt) + len(poi) == 26:
				errors.append("- None<br>\n")
			else:
				errors += sources_text
				errors += proj_txt
				if len(poi) > 26:
					poi = poi[:len(poi) - 2] + "<br>\n"
					errors.append(poi)
			
			errors.append("</p><br>\n")
			print("Done")
		errors.append("<hr />")
	 	
		print("Merging...")
		# Merge all the merged pdfs from buildGraph
		wfo_merged = sorted(glob.glob(f"results/{region}/*.pdf"))
		merge(wfo_merged, f"results/{region}_final.pdf", False, TEST)


		bookmarks(f"results/{region}_final.pdf", TEST)
		
		'''	
		print("Adding bookmarks...")
		pdf_out = PdfFileWriter() # open output
		pdf_in = PdfFileReader(f"results/{region}_final.pdf",  strict = False) # open input


		n = pdf_in.getNumPages()

		for i in range(n):
		  pdf_out.addPage(pdf_in.getPage(i)) # insert page
		# Set the bookmarks by WFO->Verif Type->Element->Issuance->Stat->Threshold using nested dictionaries to store pages
		for wfo in toc_wfos:
			lvl1 = pdf_out.addBookmark(f"{wfo}: {wfos['regions'][region][wfo]}", toc_wfos[wfo][0], parent=None, collapse=True)
			for vtype in toc_wfos[wfo][1]:
				lvl2 = pdf_out.addBookmark(vtype, toc_wfos[wfo][1][vtype][0], parent=lvl1, collapse=True)
				for element in toc_wfos[wfo][1][vtype][1]:
					lvl3 = pdf_out.addBookmark(element, toc_wfos[wfo][1][vtype][1][element]['page'], parent=lvl2, collapse=True)
					iss_idx = toc_wfos[wfo][1][vtype][1][element]['page']
					for issuance in toc_wfos[wfo][1][vtype][1][element]['issuances']:
						lvl4 = pdf_out.addBookmark(f'NDFD {issuance}', iss_idx, parent=lvl3, collapse=True)
						stat_idx = 0
						for stat in toc_wfos[wfo][1][vtype][1][element]['stats']:
							lvl5 = pdf_out.addBookmark(stat, (iss_idx + stat_idx), parent=lvl4, collapse=True)
							thresh_idx = 0
							if len(toc_wfos[wfo][1][vtype][1][element]['thresholds'][issuance]) > 1:
								for threshold in toc_wfos[wfo][1][vtype][1][element]['thresholds'][issuance]:
									pdf_out.addBookmark(threshold, (iss_idx + stat_idx) + thresh_idx, parent=lvl5, collapse=True)
									thresh_idx += 1
							stat_idx += len(toc_wfos[wfo][1][vtype][1][element]['thresholds'][issuance])
						iss_idx += stat_idx

		
		

		print("Writing...")
		# Write the final pdf
		outputStream = open(f"results/{region}_final.pdf",'wb') #creating result pdf JCT
		pdf_out.setPageMode("/UseOutlines")
		pdf_out.write(outputStream) #writing to result pdf JCT
		outputStream.close() #closing result JCT
		'''
		print("Building report...")
		

		# Write the projections summary at the top of the region
		build_text = ""
		proj_summary = "<ul>"
		for source in missingProj:
			if missingProj[source]["expected"] > missingProj[source]["observed"]:
				proj_summary += f"<li>Missing {missingProj[source]['expected'] - missingProj[source]['observed']}/{missingProj[source]['expected']} ({round(100*(missingProj[source]['expected'] - missingProj[source]['observed'])/missingProj[source]['expected'], 1)}%) {source} projections across {region}</li>"
		proj_summary += "</ul>"
		errors.insert(1, proj_summary)

		common = 0
		uncommon = 0
		rare = 0
		errors.insert(1, f"<p style='text-align: center;'>Total <span style='color: #008000;'>Common</span>: C_PLACEHOLDER&nbsp; &nbsp; &nbsp; &nbsp;Total <span style='color: #dbbb07;'>Uncommon</span>: U_PLACEHOLDER&nbsp; &nbsp; &nbsp; &nbsp;Total <span style='color: #e30000;'>Rare</span>: R_PLACEHOLDER</p>")
		# Calculate the occurences of each projection/source return error and flag it
		for error in errors:
			if "Missing" in error and "across" not in error:
				if "return" not in error:
					x = error.split(" ", 4)
					count = len([line for line in errors if x[4:][0] in line])
				else:
					count = errors.count(error)

				if count > 2:
					error += f" - <span style='color: #008000;'>Common</span><br>\n"
					common += 1
				elif count > 1:
					error += f" - <span style='color: #dbbb07;'>Uncommon</span><br>\n"
					uncommon += 1
				else:
					error += f" - <span style='color: #e30000;'>Rare</span><br>\n"
					rare += 1
			
			build_text += error

		build_text = build_text.replace("C_PLACEHOLDER", str(common))
		build_text = build_text.replace("U_PLACEHOLDER", str(uncommon))
		build_text = build_text.replace("R_PLACEHOLDER", str(rare))

		print(f"{region} finished")

		# Stop timer
		stop = timeit.default_timer()
		execution_time = stop - start
		print("Program Executed in "+str(execution_time)) # It returns time in seconds


	# Add generated message to email
	tz_NY = pytz.timezone('America/New_York')
	now = datetime.now(tz_NY)
	dt_string = now.strftime("%Y-%m-%d %H:%M:%S")
	build_text += f"<p style='text-align: center;'><span style='color: #808080;'>Generated: {dt_string} EST</span></p>"
	if MONTHLY:
		sendReport(build_text, DATE)	
	else:
		subject_string = DATE_START + " - " + DATE_END
		sendReport(build_text, subject_string)	

	# Remove tmp folder
	#shutil.rmtree("tmp")
	snapshot = tracemalloc.take_snapshot()
	display_top(snapshot)
	load1, load5, load15 = psutil.getloadavg()

	cpu_usage = (load15/os.cpu_count()) * 100
	print('cpu_usage: ', cpu_usage)
	print('RAM memory % used:', psutil.virtual_memory()[2])


if __name__ == "__main__":
    main()