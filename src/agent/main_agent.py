import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import AgentExecutor, create_openai_tools_agent

# No longer need to modify sys.path with the src structure
from src.agent.tools import (
    get_pro_player_average_stat,
    get_user_average_stat,
    get_best_champions_from_pros,
    get_pro_build_for_champion,
    find_critical_moments_in_game,
    analyze_vision_control,
    analyze_build_path,
    analyze_teamfight_positioning,
    analyze_item_gold_spend,
    get_laning_phase_stats,
    get_common_skill_order_for_champion,
    analyze_objective_proximity,
    determine_playstyle,
    get_latest_match_id,
    generate_pathing_map_for_match,
    analyze_performance_trend,
    get_pro_matchup_advice,
    analyze_gold_efficiency
)

# Load environment variables
load_dotenv()

def create_agent_executor():
    """
    Creates and returns the LangChain agent executor, now with an improved prompt.
    """
    try:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        dotenv_path = os.path.join(project_root, '.env')
        load_dotenv(dotenv_path=dotenv_path)

        if not os.getenv("GOOGLE_API_KEY"):
            print("ERROR: GOOGLE_API_KEY not found in .env file.")
            return None

        tools = [
            get_pro_player_average_stat, get_user_average_stat, get_best_champions_from_pros,
            get_pro_build_for_champion, find_critical_moments_in_game, analyze_vision_control,
            analyze_build_path, analyze_teamfight_positioning, analyze_item_gold_spend,
            get_laning_phase_stats, get_common_skill_order_for_champion, determine_playstyle,
            analyze_objective_proximity, get_latest_match_id, analyze_performance_trend,
            get_pro_matchup_advice, analyze_gold_efficiency
        ]

        llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro-latest", temperature=0.2, convert_system_message_to_human=True)

        # --- NEW, MORE INTELLIGENT PROMPT ---
        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "You are an expert League of Legends support coach. Your primary goal is to provide clear, actionable, and data-driven advice to players."
                "BE PROACTIVE: Before you ask the user for information, first try to find it yourself using your tools. "
                "For example, if the user asks about their 'last game' or 'latest match', you MUST use the 'get_latest_match_id' tool to find it. "
                "Do not ask for the champion name if you can find it through the match data."

                "CHAIN YOUR TOOLS: You can and should use the output of one tool as the input for another. "
                "For example, get the latest match ID, then use that ID to get comprehensive game stats, and then use those stats to give the user tips."

                "SYNTHESIZE AND ADVISE: Don't just report stats. Your main purpose is to interpret the data and give concrete, actionable advice. "
                "Explain what the numbers mean. For example, if vision score is low, suggest specific warding locations or timings."

                "MARKDOWN FOR ITEMS: When you list items from a build path or build summary, you MUST display them using Markdown image syntax. "
                "For each item, get its name and image_url from your tools and format it exactly like this: `![Item Name](image_url) Item Name`"
            )),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ])

        agent = create_openai_tools_agent(llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

        return agent_executor

    except Exception as e:
        print(f"ERROR: Failed to create agent executor: {e}")
        return None
    

if __name__ == '__main__':
    support_coach_agent = create_agent_executor()
    
    print("--- Support Coach Agent Initialized ---")
    print("What would you like to analyze?")
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            break
        
        # Example of a contextual prompt for direct testing
        contextual_prompt = (
            f"For the user with game_name='G2 Labrov' and tag_line='GR1', "
            f"answer the following question: {user_input}"
        )
        
        result = support_coach_agent.invoke({"input": contextual_prompt})
        print(f"Coach: {result['output']}")