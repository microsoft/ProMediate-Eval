# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Text splitting utilities using spaCy."""
from typing import List
import spacy
from spacy.language import Language

class SentenceSplitter:
    """Split text into sentences using spaCy's sentencizer component."""
    
    def __init__(self, model_name: str = "en_core_web_sm"):
        """Initialize the spaCy-based sentence splitter.
        
        Args:
            model_name: Name of the spaCy model to use (default: en_core_web_sm)
        """
        try:
            self.nlp = spacy.load(model_name, disable=["tagger", "parser", "ner", "lemmatizer", "attribute_ruler"])
        except OSError:
            # If the model is not found, download a lightweight pipeline with just the sentencizer
            self.nlp = spacy.blank("en")
        
        # Make sure the sentencizer is added to the pipeline
        if "sentencizer" not in self.nlp.pipe_names:
            sentencizer = self.nlp.add_pipe("sentencizer")
    
    def split_sentences(self, text: str) -> List[str]:
        """Split text into sentences using spaCy.
        
        Args:
            text: Text to split
            
        Returns:
            List of sentences
        """
        if not text:
            return []
        
        doc = self.nlp(text)
        return [sent.text.strip() for sent in doc.sents]
    
    def split_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs based on double newlines.
        
        Args:
            text: Text to split
            
        Returns:
            List of paragraphs
        """
        if not text:
            return []
        
        return [p.strip() for p in text.split("\n\n") if p.strip()]
    
    def split_text(self, text: str, by_paragraphs: bool = True) -> List[str]:
        """Split text into sentences and optionally paragraphs.
        
        Args:
            text: Text to split
            by_paragraphs: Whether to split by paragraphs first (default: True)
            
        Returns:
            List of text chunks
        """
        if not text:
            return []
        
        if by_paragraphs:
            # First split by paragraphs, then by sentences within each paragraph
            paragraphs = self.split_paragraphs(text)
            result = []
            for paragraph in paragraphs:
                result.extend(self.split_sentences(paragraph))
            return result
        else:
            # Just split by sentences
            return self.split_sentences(text)
