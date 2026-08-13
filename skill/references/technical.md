# Technical module

Use adjusted daily OHLCV and an explicit as-of date. Calculate EMA(5/10/20), SMA(50/200), RSI(14) with Wilder smoothing, MACD(12,26,9), Bollinger(20,2), ATR(14), and a close-price-weighted volume histogram.

Call the histogram “close-price weighted volume nodes”; it is not a true volume profile because daily volume is not allocated across each bar's high-low range. Only call a true volume profile when intraday bars or trades are available and the binning rule is explicit.

MA compression is a state, not a bullish score. Set direction to neutral when the fastest/slowest spread is compressed; require breakout direction, volume, and relative strength for directional interpretation. RSI oversold is not a reversal signal without confirmation.
