#!/usr/bin/env python3
"""
🚀 STEP 3: Create Educational Training Datasets
Generates specialized datasets for educational fine-tuning
"""

import json
import random
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

class EducationalDatasetCreator:
    """Creates comprehensive educational training datasets"""
    
    def __init__(self):
        self.datasets_dir = Path("./datasets")
        self.datasets_dir.mkdir(exist_ok=True)
        
    def create_tutoring_dataset(self) -> List[Dict]:
        """Create tutoring conversation dataset"""
        
        tutoring_examples = [
            {
                "instruction": "Explain calculus derivatives to a struggling student",
                "input": "I don't understand what a derivative actually means. The textbook just shows formulas.",
                "output": "Think of a derivative as asking 'how fast is something changing right now?' Imagine you're driving - your speedometer shows your speed (how fast your distance is changing). A derivative is like a mathematical speedometer! For x², as x grows, the 'speed' of growth is 2x. At x=3, it's growing at rate 6. At x=5, it's growing at rate 10. The derivative tells you the rate of change at any point!"
            },
            {
                "instruction": "Help a student understand photosynthesis",
                "input": "What is photosynthesis and why is it important?",
                "output": "Photosynthesis is like a plant's way of making food using sunlight! Here's the simple version: Plants take in CO₂ from air and H₂O from soil, then use sunlight energy to combine them into glucose (sugar) and release O₂. Think of it as: 6CO₂ + 6H₂O + sunlight → C₆H₁₂O₆ + 6O₂. It's crucial because: 1) Plants make their own food, 2) We get oxygen to breathe, 3) It's the base of all food chains!"
            },
            {
                "instruction": "Explain programming loops to a beginner",
                "input": "I'm confused about for loops in Python. When do I use them?",
                "output": "A for loop is like giving someone a list of tasks and saying 'do this for each item.' Use it when you know exactly what you want to repeat over. Example: 'for each student in the class, print their name' or 'for each number from 1 to 10, multiply by 2.' The pattern is: for item in collection: do_something(item). It's perfect when you have a specific set of things to work with, unlike while loops which continue until a condition changes."
            },
            {
                "instruction": "Help with algebra word problems",
                "input": "I hate word problems. I never know how to start them.",
                "output": "Word problems are just stories with hidden math! Here's a simple strategy: 1) Read twice - first for the story, second for numbers and what they're asking. 2) Identify what you don't know (this becomes your variable). 3) Find relationships between known and unknown values. 4) Translate English to math equations. 5) Solve the equation. Example: 'John has 3 more apples than Sarah. Together they have 15.' Let Sarah's apples = x, then John = x+3, so x + (x+3) = 15. Much easier when you break it down!"
            },
            {
                "instruction": "Explain the water cycle simply",
                "input": "The water cycle seems complicated with all these big words.",
                "output": "The water cycle is just water going on a journey! Think of it as a circle: 1) EVAPORATION: Sun heats water (oceans, rivers) and it becomes invisible water vapor, rising up. 2) CONDENSATION: High up, it gets cold and vapor becomes tiny water droplets in clouds. 3) PRECIPITATION: Clouds get heavy and drop water as rain, snow, or hail. 4) COLLECTION: Water flows back to oceans and rivers. Then it starts over! It's like nature's recycling system - the same water has been cycling for millions of years!"
            },
            {
                "instruction": "Help with essay writing structure",
                "input": "My essays are always messy and don't flow well. How do I organize them?",
                "output": "Think of an essay like a sandwich! 🥪 Top bun = INTRODUCTION (hook + thesis). Meat & toppings = BODY PARAGRAPHS (each with one main idea + evidence + explanation). Bottom bun = CONCLUSION (restate thesis + summarize + final thought). Each body paragraph follows PEE: Point (topic sentence), Evidence (quotes/facts), Explanation (how it supports your thesis). The secret is outlining first: decide your main points, then flesh them out. This gives you a roadmap so you never get lost while writing!"
            },
            {
                "instruction": "Explain fractions in a relatable way",
                "input": "Fractions are confusing. Why do we multiply to divide?",
                "output": "Imagine fractions as pizza slices! 🍕 3/4 means 3 slices out of 4 total. When dividing fractions, you're asking 'how many groups of this size fit in that?' Like: how many 1/2 pizzas can you make from 2 whole pizzas? Answer: 4! The 'flip and multiply' trick works because dividing by 1/2 is the same as asking 'how many halves are there?' which is multiplying by 2. Dividing by a fraction = multiplying by its reciprocal. It's a shortcut that always works!"
            },
            {
                "instruction": "Help with chemistry balancing equations",
                "input": "Balancing chemical equations is impossible. I never get the right numbers.",
                "output": "Balancing equations is like balancing a scale - same number of each type of atom on both sides! Start simple: 1) Count atoms of each element on both sides. 2) Start with the most complex molecule. 3) Use whole number coefficients only. 4) Save hydrogen and oxygen for last. Example: H₂ + O₂ → H₂O. Left: 2H, 2O. Right: 2H, 1O. Need more O on right, so 2H₂O. Now: Left needs 4H, so 2H₂. Final: 2H₂ + O₂ → 2H₂O. Practice with simple ones first!"
            },
            {
                "instruction": "Explain historical cause and effect",
                "input": "Why did World War 1 start? It seems like it was just one assassination.",
                "output": "Great question! The assassination was just the spark, not the cause. Think of it like a pile of dry wood (tensions) waiting for a match (assassination). The real causes: 1) MILITARISM: Countries were building massive armies. 2) ALLIANCES: 'If you fight my friend, you fight me' agreements. 3) IMPERIALISM: Competition for colonies. 4) NATIONALISM: Ethnic groups wanting independence. When Archduke Franz Ferdinand was shot, the alliance system meant one conflict triggered everyone's obligations. It was like dominoes falling - one event triggered a chain reaction because the conditions were already set."
            },
            {
                "instruction": "Help with scientific method understanding",
                "input": "What's the point of the scientific method? Why can't we just observe and conclude?",
                "output": "The scientific method prevents us from fooling ourselves! Humans are great at seeing patterns that aren't really there. The method is like a quality check: 1) OBSERVE: What's happening? 2) QUESTION: Why is this happening? 3) HYPOTHESIS: Educated guess about why. 4) EXPERIMENT: Test your guess under controlled conditions. 5) ANALYZE: Do results support your hypothesis? 6) CONCLUDE: Was your guess right? The key is CONTROLLED testing - changing only one thing at a time so you know what caused the results. Without this process, we might conclude that roosters cause sunrise just because they crow before it happens!"
            }
        ]
        
        # Add more examples programmatically
        math_topics = ["algebra", "geometry", "trigonometry", "statistics"]
        science_topics = ["physics", "chemistry", "biology", "earth science"]
        programming_topics = ["variables", "functions", "data structures", "algorithms"]
        
        additional_examples = []
        
        for topic in math_topics:
            additional_examples.append({
                "instruction": f"Explain {topic} concepts to a beginner",
                "input": f"I'm struggling with {topic} and don't know where to start.",
                "output": f"Let's break {topic} down into manageable pieces. The key is starting with the fundamentals and building up. Think of {topic} as a toolkit - each concept is a tool that helps solve different types of problems. We'll start with the basics and show you how they connect to create a complete understanding."
            })
            
        tutoring_examples.extend(additional_examples)
        return tutoring_examples
        
    def create_content_classification_dataset(self) -> List[Dict]:
        """Create content classification dataset for feed algorithm"""
        
        content_examples = [
            {
                "content": {
                    "type": "video",
                    "title": "How Photosynthesis Works - 3 Minute Explanation",
                    "description": "Simple breakdown of photosynthesis process for high school students",
                    "duration": 180,
                    "tags": ["biology", "science", "photosynthesis", "education"],
                    "creator_verified": True
                },
                "classification": "educational",
                "educational_value": 0.95,
                "engagement_prediction": 0.78,
                "target_audience": "high_school",
                "learning_objectives": ["understand photosynthesis", "learn cellular processes"]
            },
            {
                "content": {
                    "type": "video",
                    "title": "Crazy TikTok Dance Challenge #viral",
                    "description": "New dance trend everyone's doing",
                    "duration": 30,
                    "tags": ["dance", "viral", "trending", "fun"],
                    "creator_verified": False
                },
                "classification": "entertainment",
                "educational_value": 0.05,
                "engagement_prediction": 0.92,
                "target_audience": "general",
                "learning_objectives": []
            },
            {
                "content": {
                    "type": "video",
                    "title": "Python Functions Explained with Real Examples",
                    "description": "Learn Python functions through practical coding examples",
                    "duration": 420,
                    "tags": ["programming", "python", "tutorial", "coding"],
                    "creator_verified": True
                },
                "classification": "educational",
                "educational_value": 0.88,
                "engagement_prediction": 0.65,
                "target_audience": "programming_beginners",
                "learning_objectives": ["understand functions", "write reusable code"]
            },
            {
                "content": {
                    "type": "image",
                    "title": "Mathematical Beauty: Fibonacci in Nature",
                    "description": "Visual examples of Fibonacci sequence in flowers, shells, and galaxies",
                    "tags": ["mathematics", "nature", "fibonacci", "patterns"],
                    "creator_verified": True
                },
                "classification": "educational",
                "educational_value": 0.82,
                "engagement_prediction": 0.73,
                "target_audience": "math_enthusiasts",
                "learning_objectives": ["recognize mathematical patterns", "appreciate math in nature"]
            },
            {
                "content": {
                    "type": "video",
                    "title": "Study With Me - 2 Hour Focus Session",
                    "description": "Quiet study session with ambient sounds",
                    "duration": 7200,
                    "tags": ["study", "focus", "productivity", "ambient"],
                    "creator_verified": True
                },
                "classification": "study_support",
                "educational_value": 0.70,
                "engagement_prediction": 0.85,
                "target_audience": "students",
                "learning_objectives": ["maintain focus", "study effectively"]
            }
        ]
        
        return content_examples
        
    def create_learning_path_dataset(self) -> List[Dict]:
        """Create learning path generation dataset"""
        
        learning_paths = [
            {
                "goal": "Master machine learning from scratch",
                "current_level": "beginner",
                "time_available": 90,  # days
                "learning_style": "hands-on",
                "path": [
                    {
                        "week": 1,
                        "topic": "Python Fundamentals",
                        "description": "Variables, loops, functions, data structures",
                        "resources": ["Python tutorial videos", "Coding exercises"],
                        "milestone": "Build a calculator program"
                    },
                    {
                        "week": 2,
                        "topic": "Mathematics for ML",
                        "description": "Linear algebra, statistics, probability",
                        "resources": ["Khan Academy math", "NumPy tutorials"],
                        "milestone": "Solve matrix operations"
                    },
                    {
                        "week": 3,
                        "topic": "Data Manipulation",
                        "description": "Pandas, data cleaning, visualization",
                        "resources": ["Pandas documentation", "Matplotlib tutorials"],
                        "milestone": "Analyze a real dataset"
                    },
                    {
                        "week": 4,
                        "topic": "Supervised Learning",
                        "description": "Linear regression, classification",
                        "resources": ["Scikit-learn tutorials", "Kaggle courses"],
                        "milestone": "Build a prediction model"
                    }
                ]
            },
            {
                "goal": "Prepare for SAT Math",
                "current_level": "junior_high",
                "time_available": 120,  # days
                "learning_style": "practice-focused",
                "path": [
                    {
                        "week": 1,
                        "topic": "Algebra Review",
                        "description": "Equations, inequalities, functions",
                        "resources": ["Algebra practice tests", "Khan Academy"],
                        "milestone": "Score 80%+ on algebra diagnostic"
                    },
                    {
                        "week": 2,
                        "topic": "Geometry Fundamentals",
                        "description": "Area, perimeter, angles, triangles",
                        "resources": ["Geometry workbook", "Visual proofs"],
                        "milestone": "Master basic geometric formulas"
                    },
                    {
                        "week": 3,
                        "topic": "Advanced Algebra",
                        "description": "Quadratics, exponentials, radicals",
                        "resources": ["Practice problems", "Video explanations"],
                        "milestone": "Solve complex equations confidently"
                    }
                ]
            }
        ]
        
        return learning_paths
        
    def create_search_enhancement_dataset(self) -> List[Dict]:
        """Create search query understanding dataset"""
        
        search_examples = [
            {
                "query": "how to solve quadratic equations",
                "intent": "learning_tutorial",
                "subject": "mathematics",
                "difficulty": "intermediate",
                "enhanced_results": [
                    "Step-by-step quadratic formula tutorial",
                    "Interactive quadratic equation solver",
                    "Visual representation of parabolas",
                    "Practice problems with solutions"
                ],
                "learning_path_suggestions": [
                    "Review algebra basics first",
                    "Practice factoring polynomials",
                    "Learn graphing techniques"
                ]
            },
            {
                "query": "photosynthesis for kids",
                "intent": "simplified_explanation",
                "subject": "biology",
                "difficulty": "elementary",
                "enhanced_results": [
                    "Animated photosynthesis video for children",
                    "Simple diagram of plant processes",
                    "Interactive plant growth game",
                    "Fun facts about plants for kids"
                ],
                "learning_path_suggestions": [
                    "Start with plant parts identification",
                    "Learn about sunlight and water",
                    "Explore plant lifecycle"
                ]
            },
            {
                "query": "python debugging tips",
                "intent": "problem_solving",
                "subject": "programming",
                "difficulty": "intermediate",
                "enhanced_results": [
                    "Common Python debugging techniques",
                    "IDE debugging tools tutorial",
                    "Error message interpretation guide",
                    "Best practices for code testing"
                ],
                "learning_path_suggestions": [
                    "Master basic Python syntax",
                    "Learn about error types",
                    "Practice code review techniques"
                ]
            }
        ]
        
        return search_examples
        
    def save_datasets(self):
        """Save all datasets to files"""
        
        print("🚀 STEP 3: CREATING EDUCATIONAL TRAINING DATASETS")
        print("=" * 60)
        
        datasets = {
            "tutoring_conversations": self.create_tutoring_dataset(),
            "content_classification": self.create_content_classification_dataset(),
            "learning_paths": self.create_learning_path_dataset(),
            "search_enhancement": self.create_search_enhancement_dataset()
        }
        
        for name, data in datasets.items():
            file_path = self.datasets_dir / f"{name}.json"
            
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
                
            print(f"✅ Created {name}: {len(data)} examples -> {file_path}")
            
        # Create combined training dataset
        combined_training = []
        
        # Convert tutoring to training format
        for example in datasets["tutoring_conversations"]:
            combined_training.append({
                "text": f"<|im_start|>system\nYou are a helpful educational tutor.<|im_end|>\n<|im_start|>user\n{example['instruction']}\n{example['input']}<|im_end|>\n<|im_start|>assistant\n{example['output']}<|im_end|>"
            })
            
        # Convert content classification to training format
        for example in datasets["content_classification"]:
            content_str = json.dumps(example["content"])
            combined_training.append({
                "text": f"<|im_start|>system\nAnalyze content for educational value and engagement.<|im_end|>\n<|im_start|>user\nClassify this content: {content_str}<|im_end|>\n<|im_start|>assistant\nClassification: {example['classification']}\nEducational Value: {example['educational_value']}\nEngagement Prediction: {example['engagement_prediction']}<|im_end|>"
            })
            
        combined_path = self.datasets_dir / "combined_training.json"
        with open(combined_path, 'w') as f:
            json.dump(combined_training, f, indent=2)
            
        print(f"✅ Created combined_training: {len(combined_training)} examples -> {combined_path}")
        
        # Create metadata
        metadata = {
            "created_at": datetime.now().isoformat(),
            "total_examples": sum(len(data) for data in datasets.values()),
            "datasets": {name: len(data) for name, data in datasets.items()},
            "combined_training_examples": len(combined_training),
            "ready_for_fine_tuning": True
        }
        
        metadata_path = self.datasets_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
            
        print(f"✅ Created metadata: {metadata_path}")
        
        print("\n🎉 STEP 3 COMPLETE: EDUCATIONAL DATASETS CREATED!")
        print("=" * 60)
        print(f"📊 Total Examples: {metadata['total_examples']}")
        print(f"📁 Dataset Directory: {self.datasets_dir}")
        print(f"🚀 Ready for Step 4: LoRA Fine-tuning")
        
        return metadata

def main():
    creator = EducationalDatasetCreator()
    metadata = creator.save_datasets()
    
    print("\n✅ Step 3 completed successfully!")
    print("🔄 Ready to proceed to Step 4...")
    
    return metadata

if __name__ == "__main__":
    main()
