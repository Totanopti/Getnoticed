from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
import keepa
import openai
import pprint
import uuid
from typing import Dict, Any

# Initialize API
app = FastAPI(title="Amazon FBA Analyzer API")

# API keys configuration (use environment variables in production)
keepa_api_key = '7hmcbb7q1m72lsrnv8m7ka81eum391tiv37g7qgue731e54f02nacqeo05uq8qrs'
openai_api_key = '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'

# Initialize APIs
keepa_api = keepa.Keepa(keepa_api_key)
openai_client = openai.Client(api_key=openai_api_key)

# Session storage (use Redis in production)
active_sessions = {}

# Request models
class AnalysisRequest(BaseModel):
    asin: str

class ChatRequest(BaseModel):
    session_id: str
    question: str

class AmazonFBAAnalyzer:
    def __init__(self):
        self.current_analysis = None
        self.chat_history = []
        self.keepa_api = keepa_api
        self.openai_client = openai_client

    def calculate_profitability_score(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate the full profitability score"""
        scores = {
            'amazon_on_listing': -4 if analysis['Amazon on Listing']['Value'] == 'Yes' else 4,
            'fba_sellers': -4 if analysis['FBA Sellers']['Count'] >= 4 else 4,
            'buy_box_eligible': 4 if analysis['Buy Box Eligible']['Value'] == 'Yes' else -4,
            'variation_listing': -4 if analysis['Variation Listing']['Value'] == 'Yes' else 4,
            'sales_rank_trend': analysis['Sales Rank']['Impact'],
            'estimated_demand': analysis['Estimated Demand']['Impact'],
            'offer_count': -4 if analysis['Offer Count']['Total'] >= 4 else 4
        }
        
        total_score = sum(scores.values())
        max_score = 38
        final_score = round((total_score / max_score) * 10, 1)
        
        category = "High Profitability" if final_score >=7 else \
                 "Moderate Profitability" if final_score >=4 else \
                 "Low Profitability"
        
        analysis['Profitability Score'] = {
            'Final Score (1-10)': final_score,
            'Category': category,
            'Score Breakdown': scores,
            'Total Raw Score': total_score,
            'Max Possible Score': max_score
        }
        return analysis

    def get_product_analysis(self, asin: str) -> Dict[str, Any]:
        """Fetch product data and perform analysis"""
        products = self.keepa_api.query([asin])
        if not products:
            return None
            
        product = products[0]
        
        analysis = {
            "ASIN": product.get('asin', 'N/A'),
            "Title": product.get('title', 'N/A'),
            "Amazon on Listing": {
                "Value": "Yes" if product.get('data', {}).get('offer', {}).get('isAmazon', False) else "No",
                "Impact": -4 if product.get('data', {}).get('offer', {}).get('isAmazon', False) else 4
            },
            "FBA Sellers": {
                "Count": product.get('data', {}).get('offer', {}).get('fbaOfferCount', 0),
                "Impact": -4 if product.get('data', {}).get('offer', {}).get('fbaOfferCount', 0) >= 4 else 4
            },
            "Buy Box Eligible": {
                "Value": "Yes" if product.get('data', {}).get('offer', {}).get('isBuyBoxWinner', False) else "No",
                "Impact": 4 if product.get('data', {}).get('offer', {}).get('isBuyBoxWinner', False) else -4
            },
            "Variation Listing": {
                "Value": "Yes" if product.get('variations', []) else "No",
                "Impact": -4 if product.get('variations', []) else 4
            },
            "Sales Rank": {
                "Current": product.get('data', {}).get('stats', {}).get('current', {}).get('salesRank', 'N/A'),
                "Trend": "Decreasing" if product.get('data', {}).get('stats', {}).get('avg', {}).get('salesRank', {}).get('delta', 0) < 0 else "Increasing",
                "Impact": 4 if product.get('data', {}).get('stats', {}).get('avg', {}).get('salesRank', {}).get('delta', 0) < 0 else -4
            },
            "Estimated Demand": {
                "Value": "High" if product.get('data', {}).get('stats', {}).get('current', {}).get('salesRank', 999999) < 10000 else "Low",
                "Impact": 5 if product.get('data', {}).get('stats', {}).get('current', {}).get('salesRank', 999999) < 10000 else -5
            },
            "Offer Count": {
                "Total": product.get('data', {}).get('offer', {}).get('offerCount', 0),
                "Impact": -4 if product.get('data', {}).get('offer', {}).get('offerCount', 0) >= 4 else 4
            }
        }
        
        return self.calculate_profitability_score(analysis)

    def generate_insights(self, analysis) -> str:
        """Generate recommendations from analysis"""
        score = analysis['Profitability Score']
        insights = [
            f"## 🔍 Product Assessment: {score['Category']}",
            f"**Profitability Score:** {score['Final Score (1-10)']}/10",
            "\n## 📊 Key Factors Analysis:"
        ]
        
        factors = {
            'Amazon on Listing': analysis['Amazon on Listing'],
            'FBA Sellers': analysis['FBA Sellers'],
            'Buy Box Eligible': analysis['Buy Box Eligible'],
            'Variation Listing': analysis['Variation Listing'],
            'Sales Rank': analysis['Sales Rank'],
            'Estimated Demand': analysis['Estimated Demand'],
            'Offer Count': analysis['Offer Count']
        }
        
        for name, data in factors.items():
            impact = data.get('Impact', 0)
            value = data.get('Value', 'N/A')
            symbol = "✅" if impact >0 else "❌" if impact <0 else "➖"
            insights.append(
                f"- {symbol} **{name}:** {value} "
                f"({'Positive' if impact >0 else 'Negative'} impact: {abs(impact)})"
            )
        
        insights.append("\n## 💡 Recommendations:")
        if score['Final Score (1-10)'] >= 7:
            insights.extend([
                "- 🚀 Strong candidate - Excellent potential for FBA",
                "- Optimize listing and pricing strategy"
            ])
        elif score['Final Score (1-10)'] >= 4:
            insights.extend([
                "- 🤔 Moderate potential - Research competitors",
                "- Calculate exact profit margins"
            ])
        else:
            insights.extend([
                "- ⚠️ High risk - Consider alternatives",
                "- Look for better scoring products"
            ])
        
        # Additional insights
        if analysis['FBA Sellers']['Count'] >=4:
            insights.append("- ⚔️ High FBA competition - Need competitive pricing")
        if analysis['Buy Box Eligible']['Value'] == 'No':
            insights.append("- 🛒 Not Buy Box eligible - Reduced sales potential")
        if analysis['Sales Rank']['Current'] != 'N/A' and analysis['Sales Rank']['Current'] > 10000:
            insights.append("- 🐢 Slow-moving product - Low demand")
        
        return "\n".join(insights)

    def query_openai(self, prompt: str) -> str:
        """Handle OpenAI queries with context"""
        if not self.current_analysis:
            return "Please analyze a product first"
            
        system_msg = {
            "role": "system",
            "content": f"Amazon FBA expert analyzing:\n{pprint.pformat(self.current_analysis)}\n\n"
                       "Tasks:\n1. Explain analysis aspects\n2. Suggest improvements\n"
                       "3. Answer FBA strategy questions\n4. Provide additional insights"
        }
        
        messages = [system_msg] + self.chat_history[-3:] + [{"role": "user", "content": prompt}]
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                temperature=0.7,
                max_tokens=500
            )
            reply = response.choices[0].message.content
            self.chat_history.extend([
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": reply}
            ])
            return reply
        except Exception as e:
            return f"OpenAI Error: {str(e)}"

# API Endpoints
@app.post("/analyze")
async def analyze_product(request: AnalysisRequest):
    """Main analysis endpoint"""
    try:
        analyzer = AmazonFBAAnalyzer()
        session_id = str(uuid.uuid4())
        analysis = analyzer.get_product_analysis(request.asin)
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Product not found")
            
        analyzer.current_analysis = analysis
        active_sessions[session_id] = analyzer
        
        return {
            "session_id": session_id,
            "score": analysis['Profitability Score'],
            "insights": analyzer.generate_insights(analysis).split("\n"),
            "factors": {
                k: v for k,v in analysis.items() 
                if k != 'Profitability Score'
            }
        }
    except Exception as e:
        raise HTTPException(500, detail=str(e))

@app.post("/chat")
async def chat_analysis(request: ChatRequest):
    """Chat with analysis context"""
    analyzer = active_sessions.get(request.session_id)
    if not analyzer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid session")
    
    try:
        response = analyzer.query_openai(request.question)
        return {
            "session_id": request.session_id,
            "response": response,
            "chat_history": analyzer.chat_history[-4:]  # Return last 2 exchanges
        }
    except Exception as e:
        raise HTTPException(500, detail=str(e))

@app.get("/session/{session_id}")
async def get_session_data(session_id: str):
    """Get complete analysis data"""
    analyzer = active_sessions.get(session_id)
    if not analyzer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid session")
    
    return {
        "analysis": analyzer.current_analysis,
        "chat_history": analyzer.chat_history
    }