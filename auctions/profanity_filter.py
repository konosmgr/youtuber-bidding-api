
import re

class ProfanityFilter:
    """Simple profanity filter for Django"""
    
    def __init__(self):
        # Common profanities - this list should be more comprehensive in production
        self.bad_words = [
            'ass', 'asshole', 'bastard', 'bitch', 'cock', 'cunt', 'damn', 'dick', 
            'fuck', 'shit', 'piss', 'slut', 'whore', 'fag', 'retard'
        ]
        
        # Compile patterns to catch variations and leetspeak
        self.patterns = []
        for word in self.bad_words:
            # Basic word
            pattern = r'\b' + re.escape(word) + r'\b'
            
            # Common letter substitutions (leetspeak)
            pattern_leet = word
            pattern_leet = pattern_leet.replace('a', '[a@4]')
            pattern_leet = pattern_leet.replace('e', '[e3]')
            pattern_leet = pattern_leet.replace('i', '[i1!]')
            pattern_leet = pattern_leet.replace('o', '[o0]')
            pattern_leet = pattern_leet.replace('s', '[s$5]')
            pattern_leet = pattern_leet.replace('t', '[t7]')
            pattern_leet = r'\b' + pattern_leet + r'\b'
            
            self.patterns.append(re.compile(pattern, re.IGNORECASE))
            self.patterns.append(re.compile(pattern_leet, re.IGNORECASE))

    def contains_profanity(self, text):
        """Check if text contains profanity"""
        if not text:
            return False
            
        # Check against all patterns
        for pattern in self.patterns:
            if pattern.search(text):
                return True
                
        return False
    
    def censor(self, text):
        """Replace profanity with asterisks"""
        if not text:
            return text
            
        result = text
        for pattern in self.patterns:
            result = pattern.sub(lambda match: '*' * len(match.group(0)), result)
            
        return result

# Create a singleton instance
profanity_filter = ProfanityFilter()