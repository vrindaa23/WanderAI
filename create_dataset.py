"""
WanderAI - Synthetic Travel Instruction Dataset Generator
=========================================================
Generates a structured JSONL dataset (`travel_dataset.jsonl`) for fine-tuning
an LLM to act as a Travel Recommendation System outputting structured JSON responses.
"""

import json
import os
import random

# Candidate dataset templates for diverse synthetic data generation
DESTINATIONS = [
    {
        "name": "Manali",
        "location": "Himachal Pradesh, India",
        "scope": "Domestic",
        "country": "India",
        "vibes": ["Mountains", "Adventure", "Relaxation"],
        "budget": "Budget",
        "coordinates": {"lat": 32.2396, "lng": 77.1887},
        "weather": "Cool summers (15-25°C) and snowy winters (-5 to 10°C).",
        "attractions": [
            {"name": "Solang Valley", "category": "Adventure", "description": "Hub for paragliding, skiing, and zorbing."},
            {"name": "Rohtang Pass", "category": "Nature", "description": "High-altitude snow pass with dramatic views."},
            {"name": "Hadimba Devi Temple", "category": "Historical", "description": "16th-century wooden temple amidst cedar forests."}
        ],
        "delicacies": [
            {"name": "Siddu", "type": "Local Bread", "description": "Steamed wheat bread stuffed with walnuts and spices."},
            {"name": "Trout Curry", "type": "Seafood", "description": "Fresh river trout cooked in Himachali herbs."}
        ]
    },
    {
        "name": "Goa",
        "location": "Goa, India",
        "scope": "Domestic",
        "country": "India",
        "vibes": ["Beaches", "Nightlife", "Relaxation"],
        "budget": "Standard",
        "coordinates": {"lat": 15.2993, "lng": 74.1240},
        "weather": "Tropical climate with warm days (28-32°C) and ocean breezes.",
        "attractions": [
            {"name": "Baga Beach", "category": "Beaches", "description": "Lively beach known for water sports and beach shacks."},
            {"name": "Basilica of Bom Jesus", "category": "Historical", "description": "UNESCO World Heritage site built in 1605."},
            {"name": "Dudhsagar Waterfalls", "category": "Nature", "description": "Spectacular 4-tiered waterfall in Bhagwan Mahaveer Sanctuary."}
        ],
        "delicacies": [
            {"name": "Goan Fish Curry Rice", "type": "Traditional", "description": "Spicy coconut curry served with steamed rice."},
            {"name": "Bebinca", "type": "Dessert", "description": "Multi-layered traditional Goan coconut pudding."}
        ]
    },
    {
        "name": "Kyoto",
        "location": "Kansai, Japan",
        "scope": "International",
        "country": "Japan",
        "vibes": ["Historical", "Relaxation", "Culture"],
        "budget": "Luxury",
        "coordinates": {"lat": 35.0116, "lng": 135.7681},
        "weather": "Pleasant in spring (cherry blossoms) and autumn (maple leaves).",
        "attractions": [
            {"name": "Fushimi Inari Shrine", "category": "Historical", "description": "Famous for thousands of vermilion torii gates."},
            {"name": "Arashiyama Bamboo Grove", "category": "Nature", "description": "Towering bamboo stalks creating a serene path."},
            {"name": "Kinkaku-ji (Golden Pavilion)", "category": "Historical", "description": "Zen temple covered in gold leaf over a pond."}
        ],
        "delicacies": [
            {"name": "Kaiseki Ryori", "type": "Fine Dining", "description": "Multi-course traditional Japanese seasonal meal."},
            {"name": "Matcha Parfait", "type": "Dessert", "description": "Uji green tea ice cream dessert layers."}
        ]
    },
    {
        "name": "Interlaken",
        "location": "Bernese Oberland, Switzerland",
        "scope": "International",
        "country": "Switzerland",
        "vibes": ["Mountains", "Adventure", "Nature"],
        "budget": "Luxury",
        "coordinates": {"lat": 46.6863, "lng": 7.8632},
        "weather": "Crisp alpine air (18-24°C in summer, sub-zero in winter).",
        "attractions": [
            {"name": "Jungfraujoch", "category": "Adventure", "description": "Top of Europe railway station at 3,454m altitude."},
            {"name": "Lake Thun & Lake Brienz", "category": "Nature", "description": "Turquoise glacial lakes with scenic steamboat cruises."},
            {"name": "Harder Kulm", "category": "Nature", "description": "Funicular viewpoint overlooking Eiger, Mönch, and Jungfrau."}
        ],
        "delicacies": [
            {"name": "Swiss Cheese Fondue", "type": "Traditional", "description": "Melted Gruyère and Vacherin cheese eaten with bread cubes."},
            {"name": "Rösti", "type": "Side Dish", "description": "Crispy pan-fried grated potato cake."}
        ]
    }
]

COMPANIONS = ["Solo", "Couple", "Family", "Friends"]
BUDGETS = ["Budget", "Standard", "Luxury"]
PACES = ["Relaxed", "Action-packed"]


def generate_itinerary(dest_name, duration, pace):
    """Generate day-by-day itinerary entries."""
    itinerary = []
    for day in range(1, duration + 1):
        if day == 1:
            title = "Arrival & City Orientation"
            activities = ["Morning: Check into hotel and relax", "Afternoon: Explore central market & neighborhood walk", "Evening: Welcome dinner at local eatery"]
        elif day == duration:
            title = "Final Highlights & Farewell"
            activities = ["Morning: Souvenir shopping & café visit", "Afternoon: Visit scenic viewpoint", "Evening: Pack up & departure transfer"]
        else:
            title = f"Day {day} Sightseeing & Local Discovery"
            activities = [f"Morning: Visit key attractions in {dest_name}", f"Afternoon: Guided {pace.lower()} activity", "Evening: Local food tasting & stroll"]
        itinerary.append({"day": day, "title": title, "activities": activities})
    return itinerary


def generate_sample(id_idx, scope, budget, companion, vibes, duration, pace, user_country="India"):
    """Generate one instruction-response pair."""
    # Filter candidates matching scope
    candidates = [d for d in DESTINATIONS if d["scope"] == scope]
    if not candidates:
        candidates = DESTINATIONS
    
    selected_dest = random.choice(candidates)
    match_score = random.randint(85, 98)

    instruction_text = (
        f"Generate travel recommendations for a {scope} trip from {user_country}. "
        f"Scope: {scope}, Budget: {budget}, Companion: {companion}, "
        f"Vibes: {', '.join(vibes)}, Duration: {duration} days, Pace: {pace}."
    )

    response_payload = {
        "recommendations": [
            {
                "id": f"rec-{id_idx}",
                "name": selected_dest["name"],
                "location": selected_dest["location"],
                "matchPercentage": match_score,
                "pitch": f"An unmissable {scope.lower()} destination tailored for a {companion.lower()} trip with a {budget.lower()} budget.",
                "coordinates": selected_dest["coordinates"],
                "weatherInsight": selected_dest["weather"],
                "budgetSplit": {"transport": 25, "stay": 40, "food": 20, "activities": 15},
                "attractions": selected_dest["attractions"],
                "localDelicacies": selected_dest["delicacies"],
                "itinerary": generate_itinerary(selected_dest["name"], duration, pace),
                "packingChecklist": [
                    {"item": "Comfortable Walking Shoes", "category": "Footwear", "packed": False},
                    {"item": "Weather-Appropriate Wear", "category": "Clothing", "packed": False},
                    {"item": "Sunscreen & Sunglasses", "category": "Essentials", "packed": False},
                    {"item": "Power Bank", "category": "Electronics", "packed": False}
                ]
            }
        ]
    }

    # Alpaca / ShareGPT instruction format
    return {
        "instruction": instruction_text,
        "input": "",
        "output": json.dumps(response_payload, indent=2)
    }


def main():
    output_filename = "travel_dataset.jsonl"
    print(f"[*] Generating synthetic travel training dataset -> {output_filename}...")
    
    samples = []
    sample_id = 1
    
    # Generate combinations
    for scope in ["Domestic", "International"]:
        for budget in BUDGETS:
            for companion in COMPANIONS:
                for pace in PACES:
                    for duration in [3, 5, 7]:
                        vibe_sample = random.sample(["Mountains", "Beaches", "Historical", "Adventure", "Relaxation"], k=2)
                        sample = generate_sample(sample_id, scope, budget, companion, vibe_sample, duration, pace)
                        samples.append(sample)
                        sample_id += 1

    # Save to JSONL file
    with open(output_filename, "w", encoding="utf-8") as f:
        for item in samples:
            f.write(json.dumps(item) + "\n")

    print(f"[+] Successfully generated {len(samples)} training pairs in '{output_filename}'.")


if __name__ == "__main__":
    main()
