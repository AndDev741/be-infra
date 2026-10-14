#!/usr/bin/env python3
"""Builds platform/monitoring/dashboards/bepresent/bepresent-immich.json; edit the queries here.

  scripts/build-bepresent-dashboard.py platform/monitoring/dashboards/bepresent/bepresent-immich.json
  scripts/build-bepresent-dashboard.py --sql   every SQL query, macros expanded, to test with psql
"""
import json, sys

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
PG = {"type": "grafana-postgresql-datasource", "uid": "immich-postgres"}

LIVE = 'a."deletedAt" IS NULL AND a.visibility <> \'hidden\''
SNAP_RE = "'^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(_overlay)?\\.(jpg|mp4|webp)$'"
LOCAL = 'a."localDateTime" AT TIME ZONE \'UTC\''

SQL = {
    "photos": f"SELECT count(*) AS \"Photos\" FROM asset a WHERE a.type = 'IMAGE' AND {LIVE}",
    "videos": f"SELECT count(*) AS \"Videos\" FROM asset a WHERE a.type = 'VIDEO' AND {LIVE}",
    "size": f"SELECT coalesce(sum(e.\"fileSizeInByte\"), 0) AS \"Library size\" FROM asset a JOIN asset_exif e ON e.\"assetId\" = a.id WHERE {LIVE}",
    "people": "SELECT count(*) AS \"People\", count(*) FILTER (WHERE coalesce(name, '') <> '') AS \"Named\" FROM person WHERE NOT \"isHidden\"",
    "places": f"SELECT count(DISTINCT e.city) AS \"Cities\", count(DISTINCT e.country) AS \"Countries\" FROM asset a JOIN asset_exif e ON e.\"assetId\" = a.id WHERE {LIVE}",
    "albums": "SELECT count(*) AS \"Albums\" FROM album WHERE \"deletedAt\" IS NULL",
    "favorites": f"SELECT count(*) AS \"Favorites\" FROM asset a WHERE a.\"isFavorite\" AND {LIVE}",
    "span": f"SELECT to_char(min({LOCAL}), 'Mon YYYY') || ' to ' || to_char(max({LOCAL}), 'Mon YYYY') AS \"Span\" FROM asset a WHERE {LIVE}",
    "snapchat": f"SELECT count(*) AS \"Snapchat memories\" FROM asset a WHERE a.\"originalFileName\" ~ {SNAP_RE} AND a.\"deletedAt\" IS NULL",
    "pipeline": f"""WITH t AS (SELECT greatest(count(*), 1) AS n FROM asset a WHERE {LIVE}),
     hevc AS (SELECT greatest(count(DISTINCT "assetId"), 1) AS n FROM asset_video WHERE "codecName" = 'hevc')
SELECT round(100.0 * (SELECT count(*) FROM asset_job_status WHERE "metadataExtractedAt" IS NOT NULL) / t.n, 1) AS "Metadata",
       round(100.0 * (SELECT count(DISTINCT "assetId") FROM asset_file WHERE type = 'thumbnail') / t.n, 1) AS "Thumbnails",
       round(100.0 * (SELECT count(*) FROM asset_file WHERE type = 'encoded_video') / hevc.n, 1) AS "HEVC videos converted",
       round(100.0 * (SELECT count(*) FROM asset_job_status WHERE "facesRecognizedAt" IS NOT NULL) / t.n, 1) AS "Faces",
       round(100.0 * (SELECT count(*) FROM smart_search) / t.n, 1) AS "Smart search",
       round(100.0 * (SELECT count(*) FROM asset_job_status WHERE "duplicatesDetectedAt" IS NOT NULL) / t.n, 1) AS "Duplicate check"
FROM t, hevc""",
    "uploads": f"""SELECT $__timeGroupAlias(a."createdAt", '10m'),
       count(*) FILTER (WHERE a."originalFileName" ~ {SNAP_RE}) AS "Snapchat import",
       count(*) FILTER (WHERE a."originalFileName" !~ {SNAP_RE}) AS "Phone and other"
FROM asset a WHERE $__timeFilter(a."createdAt") GROUP BY 1 ORDER BY 1""",
    "per_month": f"""SELECT to_char({LOCAL}, 'YYYY-MM') AS "Month",
       count(*) FILTER (WHERE a.type = 'IMAGE') AS "Photos", count(*) FILTER (WHERE a.type = 'VIDEO') AS "Videos"
FROM asset a WHERE {LIVE} GROUP BY 1 ORDER BY 1""",
    "per_year": f"""SELECT to_char({LOCAL}, 'YYYY') AS "Year",
       count(*) FILTER (WHERE a.type = 'IMAGE') AS "Photos", count(*) FILTER (WHERE a.type = 'VIDEO') AS "Videos"
FROM asset a WHERE {LIVE} GROUP BY 1 ORDER BY 1""",
    "hour": f"""SELECT lpad(extract(hour FROM {LOCAL})::int::text, 2, '0') || 'h' AS "Hour", count(*) AS "Moments"
FROM asset a WHERE {LIVE} GROUP BY 1 ORDER BY 1""",
    "weekday": f"""SELECT to_char({LOCAL}, 'ID Dy') AS "Day", count(*) AS "Moments"
FROM asset a WHERE {LIVE} GROUP BY 1 ORDER BY 1""",
    "on_this_day": f"""SELECT extract(year FROM {LOCAL})::int::text AS "Year", count(*) AS "Moments"
FROM asset a WHERE {LIVE} AND to_char({LOCAL}, 'MM-DD') = to_char(now() AT TIME ZONE 'Europe/Lisbon', 'MM-DD')
GROUP BY 1 ORDER BY 1 DESC""",
    "map": f"""SELECT e.latitude, e.longitude FROM asset a JOIN asset_exif e ON e."assetId" = a.id
WHERE e.latitude IS NOT NULL AND e.longitude IS NOT NULL AND {LIVE}""",
    "cities": f"""SELECT e.city AS "City", e.country AS "Country", count(*) AS "Moments",
       to_char(min({LOCAL}), 'YYYY-MM') AS "First", to_char(max({LOCAL}), 'YYYY-MM') AS "Last"
FROM asset a JOIN asset_exif e ON e."assetId" = a.id WHERE e.city IS NOT NULL AND {LIVE}
GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 25""",
    "countries": f"""SELECT e.country AS "Country", count(*) AS "Moments"
FROM asset a JOIN asset_exif e ON e."assetId" = a.id WHERE e.country IS NOT NULL AND {LIVE}
GROUP BY 1 ORDER BY 2 DESC""",
    "people_table": f"""SELECT coalesce(nullif(p.name, ''), '(not named yet)') AS "Person", count(DISTINCT f."assetId") AS "Photos",
       to_char(min({LOCAL}), 'YYYY-MM') AS "First seen", to_char(max({LOCAL}), 'YYYY-MM') AS "Last seen"
FROM person p
JOIN asset_face f ON f."personGroupId" = p."personGroupId" AND f."deletedAt" IS NULL
JOIN asset a ON a.id = f."assetId" AND {LIVE}
WHERE NOT p."isHidden" GROUP BY p."personGroupId", p.name ORDER BY 2 DESC LIMIT 25""",
    "faces": "SELECT count(*) AS \"Faces found\" FROM asset_face WHERE \"deletedAt\" IS NULL",
    "stacks": "SELECT count(*) AS \"Stacks\" FROM stack",
}

PANELS = []
_id = [0]


def panel(kind, title, gx, gy, w, h, ds, targets, desc="", **extra):
    _id[0] += 1
    p = {"id": _id[0], "type": kind, "title": title, "gridPos": {"x": gx, "y": gy, "w": w, "h": h},
         "datasource": ds, "targets": targets}
    if desc:
        p["description"] = desc
    p.update(extra)
    PANELS.append(p)
    return p


def row(title, gy):
    _id[0] += 1
    PANELS.append({"id": _id[0], "type": "row", "title": title, "collapsed": False,
                   "gridPos": {"x": 0, "y": gy, "w": 24, "h": 1}, "panels": []})


def sql(key, fmt="table"):
    return [{"refId": "A", "datasource": PG, "editorMode": "code", "format": fmt, "rawQuery": True,
             "rawSql": SQL[key]}]


def prom(*exprs):
    return [{"refId": chr(65 + i), "datasource": PROM, "expr": e, "legendFormat": l, "range": True}
            for i, (e, l) in enumerate(exprs)]


def thresholds(*steps):
    return {"mode": "absolute", "steps": [{"color": c, "value": v} for v, c in steps]}


def stat(title, gx, gy, w, ds, targets, unit="short", th=None, desc="", h=4, color="value", text_mode="auto"):
    return panel("stat", title, gx, gy, w, h, ds, targets, desc,
                 fieldConfig={"defaults": {"unit": unit, "thresholds": th or thresholds((None, "blue")),
                                           "color": {"mode": "thresholds"}}, "overrides": []},
                 options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                          "colorMode": color, "graphMode": "none", "textMode": text_mode,
                          "justifyMode": "center", "orientation": "auto"})


def table(title, gx, gy, w, h, key, desc=""):
    return panel("table", title, gx, gy, w, h, PG, sql(key), desc,
                 fieldConfig={"defaults": {"custom": {"align": "auto"}}, "overrides": []},
                 options={"showHeader": True, "cellHeight": "sm"})


def barchart(title, gx, gy, w, h, key, stacked=True, desc="", horizontal=False):
    return panel("barchart", title, gx, gy, w, h, PG, sql(key), desc,
                 fieldConfig={"defaults": {"color": {"mode": "palette-classic"},
                                           "custom": {"fillOpacity": 80, "lineWidth": 0}}, "overrides": []},
                 options={"stacking": "normal" if stacked else "none", "showValue": "never",
                          "orientation": "horizontal" if horizontal else "auto",
                          "xTickLabelRotation": 0 if horizontal else -45, "xTickLabelSpacing": 50,
                          "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                          "tooltip": {"mode": "multi"}, "barWidth": 0.9, "groupWidth": 0.7})


def timeseries(title, gx, gy, w, h, ds, targets, unit="short", desc="", stack=False, overrides=None, bars=False):
    custom = {"drawStyle": "bars" if bars else "line", "fillOpacity": 60 if bars else 15, "lineWidth": 1,
              "showPoints": "never", "spanNulls": True,
              "stacking": {"mode": "normal" if stack else "none", "group": "A"}}
    return panel("timeseries", title, gx, gy, w, h, ds, targets, desc,
                 fieldConfig={"defaults": {"unit": unit, "color": {"mode": "palette-classic"}, "custom": custom},
                              "overrides": overrides or []},
                 options={"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                          "tooltip": {"mode": "multi", "sort": "desc"}})


def build():
    y = 0
    # ---- Library ------------------------------------------------------------
    row("Library", y); y += 1
    stat("Photos", 0, y, 3, PG, sql("photos"))
    stat("Videos", 3, y, 3, PG, sql("videos"))
    stat("Library size", 6, y, 3, PG, sql("size"), unit="bytes", desc="Sum of the original files, as Immich read them.")
    stat("People", 9, y, 4, PG, sql("people"), desc="Face groups Immich found, and how many you named.")
    stat("Places", 13, y, 4, PG, sql("places"))
    stat("Albums", 17, y, 2, PG, sql("albums"))
    stat("Favorites", 19, y, 2, PG, sql("favorites"))
    stat("Stacks", 21, y, 3, PG, sql("stacks"), desc="Snapchat overlays stacked on top of their original.")
    y += 4
    stat("Covers", 0, y, 6, PG, sql("span"), text_mode="value", h=3)
    panel("gauge", "Snapchat import", 6, y, 6, 8, PG, sql("snapchat"),
          "Memories from the Snapchat export now in Immich (9,968 files plus 58 overlays).",
          fieldConfig={"defaults": {"min": 0, "max": 10026, "unit": "short",
                                    "thresholds": thresholds((None, "orange"), (10026, "green")),
                                    "color": {"mode": "thresholds"}}, "overrides": []},
          options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                   "showThresholdLabels": False, "showThresholdMarkers": False})
    panel("bargauge", "Processing pipeline", 12, y, 12, 8, PG, sql("pipeline"),
          "Share of the library each Immich stage has finished. Machine learning (faces, smart search) "
          "waits until metadata, thumbnails and video conversion are done (apps/immich/ml-scheduler.yaml).",
          fieldConfig={"defaults": {"min": 0, "max": 100, "unit": "percent",
                                    "thresholds": thresholds((None, "red"), (50, "orange"), (99.5, "green")),
                                    "color": {"mode": "thresholds"}}, "overrides": []},
          options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                   "orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True,
                   "valueMode": "color", "namePlacement": "left", "minVizHeight": 16})
    timeseries("Uploads (per 10 minutes)", 0, y + 3, 6, 5, PG, sql("uploads", "time_series"), bars=True, stack=True,
               desc="New assets arriving: the Snapchat importer and the phone's backup.")
    y += 8
    # ---- Moments ------------------------------------------------------------
    row("Moments", y); y += 1
    barchart("Moments per month", 0, y, 16, 9, "per_month")
    barchart("Moments per year", 16, y, 8, 9, "per_year")
    y += 9
    barchart("When you take photos (hour of day)", 0, y, 12, 7, "hour", stacked=False)
    barchart("Day of the week", 12, y, 6, 7, "weekday", stacked=False)
    table("On this day", 18, y, 6, 7, "on_this_day", "Moments taken on today's date in earlier years.")
    y += 7
    # ---- Places -------------------------------------------------------------
    row("Places", y); y += 1
    panel("geomap", "Where the moments are", 0, y, 14, 14, PG, sql("map"),
          "Every geotagged photo and video, as a heatmap.",
          fieldConfig={"defaults": {}, "overrides": []},
          options={"view": {"id": "coords", "lat": 20, "lon": -25, "zoom": 2.4, "allLayers": True},
                   "controls": {"showZoom": True, "mouseWheelZoom": True, "showAttribution": True},
                   "basemap": {"type": "default", "name": "Basemap"},
                   "layers": [{"type": "heatmap", "name": "Moments", "config": {
                       "blur": 12, "radius": 6, "weight": {"fixed": 1, "min": 0, "max": 1}},
                       "location": {"mode": "coords", "latitude": "latitude", "longitude": "longitude"},
                       "tooltip": True}],
                   "tooltip": {"mode": "details"}})
    table("Top cities", 14, y, 10, 8, "cities")
    barchart("Countries", 14, y + 8, 10, 6, "countries", stacked=False, horizontal=True)
    y += 14
    # ---- People -------------------------------------------------------------
    row("People", y); y += 1
    table("People", 0, y, 14, 9, "people_table", "Name a face group in Immich (Explore, People) and it shows here.")
    stat("Faces found", 14, y, 5, PG, sql("faces"), h=4)
    y += 9
    # ---- Server -------------------------------------------------------------
    row("Server (beyou-server)", y); y += 1
    stat("Memory available", 0, y, 4, PROM, prom(("node_memory_MemAvailable_bytes", "")), unit="bytes",
         th=thresholds((None, "red"), (500e6, "orange"), (1e9, "green")),
         desc="The ML scheduler pauses machine learning under 500 MB.")
    stat("Swap in use", 4, y, 4, PROM, prom(("node_memory_SwapTotal_bytes - node_memory_SwapFree_bytes", "")),
         unit="bytes", th=thresholds((None, "green"), (1e9, "orange"), (2e9, "red")))
    stat("Load (1 min)", 8, y, 4, PROM, prom(("node_load1", "")), unit="none",
         th=thresholds((None, "green"), (4, "orange"), (8, "red")), desc="4 threads: above 4 means work is queueing.")
    stat("CPU temperature", 12, y, 4, PROM, prom(('max(node_hwmon_temp_celsius{chip=~"platform_coretemp.*"})', "")),
         unit="celsius", th=thresholds((None, "green"), (80, "orange"), (92, "red")),
         desc="Ivy Bridge throttles at 105 °C.")
    for i, (title, mp) in enumerate([("Photo disk (HDD)", "/srv/media"), ("System disk (SSD)", "/")]):
        panel("gauge", title, 16 + 4 * i, y, 4, 4, PROM,
              prom(('100 * (1 - node_filesystem_avail_bytes{mountpoint="%s"} / node_filesystem_size_bytes{mountpoint="%s"})' % (mp, mp), "")),
              fieldConfig={"defaults": {"min": 0, "max": 100, "unit": "percent",
                                        "thresholds": thresholds((None, "green"), (75, "orange"), (90, "red")),
                                        "color": {"mode": "thresholds"}}, "overrides": []},
              options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}})
    y += 4
    timeseries("Memory", 0, y, 12, 8, PROM, prom(("node_memory_MemAvailable_bytes", "Available"),
                                                 ("node_memory_SwapTotal_bytes - node_memory_SwapFree_bytes", "Swap in use")),
               unit="bytes")
    timeseries("CPU", 12, y, 12, 8, PROM,
               prom(('sum by (mode) (rate(node_cpu_seconds_total{mode=~"user|system|iowait|nice|softirq"}[2m])) / scalar(count(node_cpu_seconds_total{mode="idle"})) * 100', "{{mode}}")),
               unit="percent", stack=True, desc="iowait is time spent waiting on disk, mostly swap and the HDD.")
    y += 8
    timeseries("Load and temperature", 0, y, 12, 8, PROM,
               prom(("node_load1", "Load 1m"), ("node_load5", "Load 5m"),
                    ('max(node_hwmon_temp_celsius{chip=~"platform_coretemp.*"})', "CPU °C")),
               overrides=[{"matcher": {"id": "byName", "options": "CPU °C"},
                           "properties": [{"id": "unit", "value": "celsius"},
                                          {"id": "custom.axisPlacement", "value": "right"},
                                          {"id": "color", "value": {"mode": "fixed", "fixedColor": "red"}}]}])
    timeseries("Disk throughput", 12, y, 12, 8, PROM,
               prom(('rate(node_disk_written_bytes_total{device="sdb"}[2m])', "HDD write"),
                    ('rate(node_disk_read_bytes_total{device="sdb"}[2m])', "HDD read"),
                    ('rate(node_disk_written_bytes_total{device="sda"}[2m])', "SSD write"),
                    ('rate(node_disk_read_bytes_total{device="sda"}[2m])', "SSD read")),
               unit="Bps")
    y += 8
    # ---- Immich and the cluster --------------------------------------------
    row("Immich and the cluster", y); y += 1
    timeseries("Immich memory", 0, y, 12, 8, PROM,
               prom(('sum by (container) (container_memory_working_set_bytes{namespace="immich", container!=""})', "{{container}}"),
                    ('sum by (container) (kube_pod_container_resource_limits{namespace="immich", resource="memory", container=~"server|machine-learning"})', "{{container}} limit")),
               unit="bytes",
               overrides=[{"matcher": {"id": "byRegexp", "options": ".* limit"},
                           "properties": [{"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [8, 6]}},
                                          {"id": "custom.fillOpacity", "value": 0}]}])
    timeseries("Immich CPU", 12, y, 12, 8, PROM,
               prom(('sum by (container) (rate(container_cpu_usage_seconds_total{namespace="immich", container!=""}[2m]))', "{{container}}")),
               unit="none", desc="In cores; the node has 4 threads.")
    y += 8
    panel("bargauge", "Restarts in the last 24 h", 0, y, 10, 7, PROM,
          prom(('sum by (namespace) (increase(kube_pod_container_status_restarts_total[24h])) > 0', "{{namespace}}")),
          "Every namespace, so Immich's effect on the other apps shows up.",
          fieldConfig={"defaults": {"unit": "none", "decimals": 0, "min": 0,
                                    "thresholds": thresholds((None, "green"), (1, "orange"), (5, "red")),
                                    "color": {"mode": "thresholds"}}, "overrides": []},
          options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                   "orientation": "horizontal", "displayMode": "basic", "showUnfilled": True})
    stat("Containers last killed by OOM", 10, y, 5, PROM,
         prom(('count(kube_pod_container_status_last_terminated_reason{reason="OOMKilled"} == 1) or vector(0)', "")),
         th=thresholds((None, "green"), (1, "red")))
    stat("Tailscale (operator + proxy)", 15, y, 5, PROM,
         prom(('sum(container_memory_working_set_bytes{namespace="tailscale", container!=""})', "")), unit="bytes")
    stat("Immich database", 20, y, 4, PG,
         [{"refId": "A", "datasource": PG, "editorMode": "code", "format": "table", "rawQuery": True,
           "rawSql": "SELECT pg_database_size('immich') AS \"Size\""}], unit="bytes")
    y += 7
    # ---- Logs ---------------------------------------------------------------
    row("Machine learning and logs", y); y += 1
    panel("logs", "ML scheduler decisions", 0, y, 12, 10, LOKI,
          [{"refId": "A", "datasource": LOKI, "expr": '{namespace="immich", container="scheduler"}'}],
          "One run every five minutes: free memory, pending work, and which queue it started or paused.",
          options={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": False})
    panel("logs", "Immich server warnings and errors", 12, y, 12, 10, LOKI,
          [{"refId": "A", "datasource": LOKI, "expr": '{namespace="immich", container="server"} |~ "(?i)(warn|error)"'}],
          options={"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending", "enableLogDetails": False})

    return {
        "uid": "bepresent-immich", "title": "bePresent · Immich", "tags": ["bepresent", "immich"],
        "description": "The photo library behind bePresent and the server it runs on.",
        "editable": True, "graphTooltip": 1, "refresh": "1m", "schemaVersion": 39, "version": 1,
        "time": {"from": "now-6h", "to": "now"}, "timezone": "browser",
        "templating": {"list": []}, "annotations": {"list": []}, "links": [
            {"title": "Open Immich", "type": "link", "url": "https://immich.tail2f18c7.ts.net", "targetBlank": True,
             "icon": "external link"}],
        "panels": PANELS,
    }


if __name__ == "__main__":
    if sys.argv[1] == "--sql":
        for k, q in SQL.items():
            q = q.replace("$__timeGroupAlias(a.\"createdAt\", '10m')", "date_bin('10 minutes', a.\"createdAt\", 'epoch') AS time")
            q = q.replace("$__timeFilter(a.\"createdAt\")", "a.\"createdAt\" > now() - interval '6 hours'")
            print("-- " + k)
            print(q.strip() + ";")
    else:
        json.dump(build(), open(sys.argv[1], "w"), indent=2, ensure_ascii=False)
        print("panels:", len(PANELS))
