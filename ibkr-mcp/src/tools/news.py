"""News and market information tools for IBKR TWS API."""

from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession
from ib_async import Stock
from ..models import AppContext


def register_news_tools(mcp: FastMCP):
    """Register news and market information tools."""
    
    @mcp.tool()
    async def ibkr_get_news_providers(
        ctx: Context[ServerSession, AppContext]
    ) -> Dict[str, Any]:
        """Get list of available news providers.
        
        Returns:
            List of news providers with codes and names
        """
        tws = ctx.request_context.lifespan_context.tws
        if not tws or not tws.is_connected():
            return {"error": "TWS client not connected"}
        
        providers = await tws.ib.reqNewsProvidersAsync()
        
        return {
            "providers": [
                {
                    "code": provider.code,
                    "name": provider.name
                }
                for provider in providers
            ],
            "count": len(providers)
        }
    
    @mcp.tool()
    async def ibkr_get_news_articles(
        ctx: Context[ServerSession, AppContext],
        symbol: str,
        providerCodes: str = "BRFUPDN",
        totalResults: int = 10,
        exchange: str = "SMART",
        currency: str = "USD",
        startDateTime: str = "",
        endDateTime: str = ""
    ) -> Dict[str, Any]:
        """Get news articles for a contract.
        
        Args:
            symbol: Contract symbol
            providerCodes: News provider codes (e.g., 'BRFUPDN', 'DJNL')
            totalResults: Maximum number of articles to retrieve
            exchange: Exchange (default: SMART)
            currency: Currency (default: USD)
            startDateTime: Optional start cursor in IBKR format, e.g. '20260807 09:30:00 US/Eastern'
            endDateTime: Optional end cursor in IBKR format, e.g. '20260807 16:00:00 US/Eastern'
            
        Returns:
            List of news articles with headlines and timestamps
        """
        tws = ctx.request_context.lifespan_context.tws
        if not tws or not tws.is_connected():
            return {"error": "TWS client not connected"}
        
        contract = Stock(symbol, exchange, currency)

        # reqHistoricalNews requires the underlying contract's real conId.
        # A newly-created Stock has conId=0 until it is qualified.  Passing
        # that unqualified contract silently produced empty MCP responses
        # even though the same TWS session could return news directly.
        try:
            qualified = await tws.ib.qualifyContractsAsync(contract)
            if not qualified or not qualified[0].conId:
                return {
                    "symbol": symbol,
                    "articles": [],
                    "count": 0,
                    "error": f"Contract could not be qualified: {symbol}",
                }

            qualified_contract = qualified[0]
            error_occurred = []

            def on_error(req_id, error_code, error_string, error_contract):
                # Farm connection notices are normal; preserve actionable IB errors.
                is_warning = error_code in {105, 110, 165, 321, 329, 399, 404, 434, 492, 10167}
                is_farm_notice = 2100 <= error_code < 2200
                if not is_warning and not is_farm_notice:
                    error_occurred.append({
                        "reqId": req_id,
                        "errorCode": error_code,
                        "errorString": error_string,
                    })

            tws.ib.errorEvent += on_error
            try:
                articles = await tws.ib.reqHistoricalNewsAsync(
                    conId=qualified_contract.conId,
                    providerCodes=providerCodes,
                    startDateTime=startDateTime,
                    endDateTime=endDateTime,
                    totalResults=totalResults
                )
            finally:
                tws.ib.errorEvent -= on_error

            if error_occurred:
                error = error_occurred[0]
                return {
                    "symbol": symbol,
                    "conId": qualified_contract.conId,
                    "articles": [],
                    "count": 0,
                    "error": f"TWS Error {error['errorCode']}: {error['errorString']}",
                }
        except Exception as exc:
            return {
                "symbol": symbol,
                "articles": [],
                "count": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        
        articles = articles or []
        return {
            "symbol": symbol,
            "conId": qualified_contract.conId,
            "providerCodes": providerCodes,
            "startDateTime": startDateTime,
            "endDateTime": endDateTime,
            "articles": [
                {
                    "time": article.time,
                    "providerCode": article.providerCode,
                    "articleId": article.articleId,
                    "headline": article.headline
                }
                for article in articles
            ],
            "count": len(articles)
        }
    
    @mcp.tool()
    async def ibkr_get_news_article(
        ctx: Context[ServerSession, AppContext],
        providerCode: str,
        articleId: str
    ) -> Dict[str, Any]:
        """Get full text of a news article.
        
        Args:
            providerCode: News provider code
            articleId: Article ID from news article list
            
        Returns:
            Full article text
        """
        tws = ctx.request_context.lifespan_context.tws
        if not tws or not tws.is_connected():
            return {"error": "TWS client not connected"}
        
        article = await tws.ib.reqNewsArticleAsync(providerCode, articleId)
        
        return {
            "providerCode": providerCode,
            "articleId": articleId,
            "articleType": article.articleType,
            "articleText": article.articleText
        }
