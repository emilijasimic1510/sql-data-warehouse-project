// Power Query > Blank query > Advanced Editor. Name this query Calendar.
// Requires the imported staging query dim_date (Enable load OFF).
let
    KnownDates = List.RemoveNulls(Table.Column(dim_date, "calendar_date")),
    FirstDate = Date.StartOfYear(Date.From(List.Min(KnownDates))),
    LastDate = Date.EndOfYear(Date.From(List.Max(KnownDates))),
    Dates = List.Dates(FirstDate, Duration.Days(LastDate - FirstDate) + 1, #duration(1,0,0,0)),
    Base = Table.FromList(Dates, Splitter.SplitByNothing(), {"Date"}),
    Typed = Table.TransformColumnTypes(Base, {{"Date", type date}}),
    Year = Table.AddColumn(Typed, "Year", each Date.Year([Date]), Int64.Type),
    MonthNumber = Table.AddColumn(Year, "Month Number", each Date.Month([Date]), Int64.Type),
    Month = Table.AddColumn(MonthNumber, "Month", each Date.ToText([Date], "MMM", "en-US"), type text),
    YearMonth = Table.AddColumn(Month, "Year Month", each Date.ToText([Date], "yyyy-MM", "en-US"), type text),
    MonthStart = Table.AddColumn(YearMonth, "Month Start", each Date.StartOfMonth([Date]), type date)
in
    MonthStart
