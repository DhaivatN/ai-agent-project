"""
app.py

Gradio interface for FitFindr. The layout and wiring are already set up —
your job is to fill in handle_query() so it calls run_agent() and maps
the session results to the three output panels.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────
def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Args:
        user_query:      The text the user typed into the search box.
        wardrobe_choice: Either "Example wardrobe" or "Empty wardrobe (new user)".

    Returns:
        A tuple of three strings:
            (listing_text, outfit_suggestion, fit_card)
        Each string maps to one of the three output panels in the UI.
    """
    # 1. Guard against empty query
    if not user_query or not user_query.strip():
        return "Please enter a search query.", "", ""

    # 2. Select wardrobe
    if wardrobe_choice == "Empty wardrobe (new user)":
        wardrobe = get_empty_wardrobe()
    else:
        wardrobe = get_example_wardrobe()

    # 3. Call agent
    session = run_agent(user_query.strip(), wardrobe)

    # 4. Handle agent error
    if session["error"]:
        return session["error"], "", ""

    # 5. Format selected item for listing panel
    item = session.get("selected_item")
    if not item:
        return "No listing was selected.", "", ""

    title = item.get("title", "Unknown item")
    price = item.get("price", "N/A")
    platform = item.get("platform", "Unknown platform")
    size = item.get("size", "Unknown size")
    condition = item.get("condition", "Unknown condition")
    category = item.get("category", "Unknown category")
    brand = item.get("brand") or "Unknown brand"
    colors = ", ".join(item.get("colors", [])) if item.get("colors") else "N/A"
    style_tags = ", ".join(item.get("style_tags", [])) if item.get("style_tags") else "N/A"
    description = item.get("description", "No description available.")

    if isinstance(price, (int, float)):
        price_text = f"${price:.0f}" if float(price).is_integer() else f"${price:.2f}"
    else:
        price_text = str(price)

    listing_text = (
        f"Title: {title}\n"
        f"Price: {price_text}\n"
        f"Platform: {platform}\n"
        f"Category: {category}\n"
        f"Size: {size}\n"
        f"Condition: {condition}\n"
        f"Brand: {brand}\n"
        f"Colors: {colors}\n"
        f"Style tags: {style_tags}\n"
        f"Description: {description}"
    )

    # Optional: include price comparison if available
    price_comparison = session.get("price_comparison")
    if price_comparison:
        assessment = price_comparison.get("price_assessment", "unknown")
        reasoning = price_comparison.get("reasoning", "")
        listing_text += (
            f"\n\nPrice check: {assessment}"
            f"\n{reasoning}"
        )

    outfit_text = session.get("outfit_suggestion") or ""
    fit_card_text = session.get("fit_card") or ""

    return listing_text, outfit_text, fit_card_text


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice],
            outputs=[listing_output, outfit_output, fitcard_output],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
