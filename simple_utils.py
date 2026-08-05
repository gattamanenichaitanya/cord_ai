# simple_utils.py - A tiny utility library

def reverse_string(text):
    """Reverses the characters in a string."""
    return text[::-1]

def count_words(sentence):
    """
    Count the whitespace-separated words in a sentence.
    
    Parameters:
    	sentence (str): The text to count words in.
    
    Returns:
    	int: The number of whitespace-separated words.
    """
    return len(sentence.split())

def celsius_to_fahrenheit(celsius):
    """
    Convert a temperature from Celsius to Fahrenheit.
    
    Parameters:
    	celsius (float): Temperature in degrees Celsius.
    
    Returns:
    	float: Equivalent temperature in degrees Fahrenheit.
    """
    return (celsius * 9/5) + 32
