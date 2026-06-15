"""
app.py

Gradio interface for FitFindr.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe
from utils.style_profile import clear_style_profile, load_style_profile, profile_summary


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str) -> tuple[str, str, str, str]:
    """
    Called by Gradio when the user submits a query.

    Returns a 4-tuple:
        (listing_text, outfit_suggestion, fit_card, extras_text)

    listing_text    — item details + retry note if search was loosened
    outfit_suggestion — trend-influenced outfit from suggest_outfit()
    fit_card        — Instagram-style caption from create_fit_card()
    extras_text     — price comparison verdict + style profile status
    """
    if not user_query or not user_query.strip():
        return "Please enter a search query.", "", "", ""

    wardrobe = (
        get_example_wardrobe()
        if wardrobe_choice == "Example wardrobe"
        else get_empty_wardrobe()
    )

    session = run_agent(user_query.strip(), wardrobe)

    # Build the extras panel regardless of success/failure
    extras_parts = []
    if session.get("price_verdict"):
        extras_parts.append(f"Price check: {session['price_verdict']}")
    if session.get("trend_context"):
        extras_parts.append(f"\nTrending now:\n{session['trend_context']}")
    if session.get("profile_summary"):
        extras_parts.append(f"\n{session['profile_summary']}")
    extras_text = "\n".join(extras_parts) if extras_parts else ""

    # Error path — show error in listing panel, leave outfit/fitcard blank
    if session["error"]:
        return session["error"], "", "", extras_text

    # Format the listing panel
    item = session["selected_item"]
    brand_line = f"Brand: {item['brand']}\n" if item.get("brand") else ""
    retry_line = f"\n⚠️ {session['retry_note']}\n" if session.get("retry_note") else ""

    listing_text = (
        f"{item['title']}\n"
        f"Price: ${item['price']:.2f} | Platform: {item['platform']} | "
        f"Size: {item['size']} | Condition: {item['condition']}\n"
        f"{brand_line}"
        f"Style: {', '.join(item['style_tags'])}\n"
        f"Colors: {', '.join(item['colors'])}"
        f"{retry_line}"
    )

    return listing_text, session["outfit_suggestion"], session["fit_card"], extras_text


def handle_clear_profile() -> str:
    """Clear the saved style profile and return updated status."""
    clear_style_profile()
    return profile_summary(load_style_profile())


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "vintage tee size XXXL under $25",    # triggers retry logic (unusual size)
    "designer ballgown size XXS under $5", # deliberate no-results test
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

        # Row 1: main three output panels
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

        # Row 2: price check, trends, and style profile
        with gr.Row():
            extras_output = gr.Textbox(
                label="🏷️ Price check · Trends · Style memory",
                lines=6,
                interactive=False,
                scale=3,
            )
            with gr.Column(scale=1):
                gr.Markdown("**Style Memory**")
                clear_btn = gr.Button("Clear saved profile", size="sm")
                clear_btn.click(fn=handle_clear_profile, outputs=[extras_output])

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        outputs = [listing_output, outfit_output, fitcard_output, extras_output]

        submit_btn.click(fn=handle_query, inputs=[query_input, wardrobe_choice], outputs=outputs)
        query_input.submit(fn=handle_query, inputs=[query_input, wardrobe_choice], outputs=outputs)

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
