import { describe, expect, it } from "vitest";
import { oldBhavcopyUrl, parseOldBhavcopyCsv } from "./old-bhavcopy";

// Real rows from NSE's 4 Jan 2021 file, plus a non-equity row and junk.
const CSV = [
  "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,",
  "20MICRONS,EQ,40.55,40.6,39.6,39.8,39.95,40.05,241109,9647424.75,04-JAN-2021,1314,INE144J01027,",
  "21STCENMGM,EQ,10.65,10.85,10.45,10.6,10.6,10.65,17191,182104.05,04-JAN-2021,854,INE253B01015,",
  "3IINFOTECH,BE,5,5.1,4.9,5.05,5.05,5,1000,5000,04-JAN-2021,10,INE748C01020,",
  "RELIANCE,EQ,1900,1950,1890,1940,1940,1895,1000000,1940000000,04-JAN-2021,50000,INE002A01018,",
  "BADROW,EQ,,,,,,,,,,,,",
].join("\n");

describe("oldBhavcopyUrl", () => {
  it("builds NSE's historical path with upper-case month", () => {
    expect(oldBhavcopyUrl(new Date(Date.UTC(2021, 0, 4)))).toBe(
      "https://nsearchives.nseindia.com/content/historical/EQUITIES/2021/JAN/cm04JAN2021bhav.csv.zip",
    );
    expect(oldBhavcopyUrl(new Date(Date.UTC(2024, 6, 5)))).toContain("/2024/JUL/cm05JUL2024bhav.csv.zip");
  });
});

describe("parseOldBhavcopyCsv", () => {
  it("keeps only EQ rows with a usable close, with NSE's printed previous close", () => {
    const rows = parseOldBhavcopyCsv(CSV);
    expect(rows.map((r) => r.symbol)).toEqual(["20MICRONS", "21STCENMGM", "RELIANCE"]);
    expect(rows[0]).toEqual({ symbol: "20MICRONS", open: 40.55, high: 40.6, low: 39.6, close: 39.8, volume: 241109, prevClose: 40.05 });
  });
  it("restricts to the allowed symbols", () => {
    expect(parseOldBhavcopyCsv(CSV, new Set(["RELIANCE"])).map((r) => r.symbol)).toEqual(["RELIANCE"]);
  });
  it("returns nothing for an empty or unrecognised file", () => {
    expect(parseOldBhavcopyCsv("")).toEqual([]);
    expect(parseOldBhavcopyCsv("<html>Access Denied</html>")).toEqual([]);
  });
});
