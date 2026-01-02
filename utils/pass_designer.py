from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import os
from datetime import datetime
from typing import Dict, Any, Optional

# Design Language Constants - Vibrant Festival Theme
PRIMARY_COLOR = "#FF1744"     # Vibrant Red/Pink
SECONDARY_COLOR = "#FF9800"   # Orange
ACCENT_COLOR = "#00BCD4"      # Cyan
YELLOW_COLOR = "#FFC107"      # Yellow
MAGENTA_COLOR = "#E91E63"     # Magenta
GREEN_COLOR = "#4CAF50"       # Green
WHITE_BG = "#FFFFFF"          # White Background
LIGHT_TEXT = "#FFFFFF"        # White Text
DARK_TEXT = "#333333"         # Dark Text for light backgrounds

class PassDesigner:
    def __init__(self):
        # Vibrant Festival Ticket Dimensions (Similar to Holi Festival)
        self.width = 1400
        self.height = 700
        self.corner_radius = 20
        self.perforation_x = 980  # Vertical tear line position (stub on right)

    def _load_fonts(self) -> Dict[str, ImageFont.FreeTypeFont]:
        """Loads high-quality typography with cross-platform fallbacks."""
        possible_paths = [
            "fonts/Helvetica-Bold.ttf",
            "Helvetica-Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "C:\\Windows\\Fonts\\arialbd.ttf",
            "arial.ttf"
        ]
        
        font_path = next((p for p in possible_paths if os.path.exists(p)), None)
        
        def get_font(size):
            try:
                if font_path:
                    return ImageFont.truetype(font_path, size)
                return ImageFont.load_default()
            except:
                return ImageFont.load_default()

        return {
            'event_title': get_font(120),    # Large event name
            'date_large': get_font(90),      # Date emphasis
            'attendee': get_font(32),        # Attendee Name
            'header': get_font(28),          # Section headers
            'body': get_font(24),            # Body text
            'label': get_font(20),           # Labels
            'small': get_font(16),           # Small text
            'footer': get_font(14)           # Footer
        }

    def create_pass_image(self, 
                          pass_data: Dict[str, Any], 
                          qr_img: Any, 
                          logo_img: Optional[Any] = None,
                          powered_by_name: str = "EVENTPASS PRO") -> bytes:
        """
        Creates a vibrant festival-style event pass image.
        pass_data expected keys: name, event_name, event_date, event_time, venue, ticket_type, sequence_number, price
        """
        # Create base with white background
        img = Image.new('RGB', (self.width, self.height), WHITE_BG)
        draw = ImageDraw.Draw(img)
        fonts = self._load_fonts()

        # Draw colorful background splashes
        self._draw_color_splashes(img, draw)
        
        # Draw main content area
        self._draw_main_content(img, draw, pass_data, fonts, logo_img)
        
        # Draw stub section
        self._draw_stub_section(img, draw, qr_img, pass_data, fonts)
        
        # Draw perforation line
        self._draw_perforation(draw)
        
        # Add decorative borders
        self._draw_decorative_borders(draw)
        
        # Output as PNG bytes
        byte_arr = io.BytesIO()
        img.save(byte_arr, format='PNG', quality=95)
        return byte_arr.getvalue()

    def _draw_color_splashes(self, img, draw):
        """Draws colorful paint splash effects in the background."""
        import random
        random.seed(42)  # Consistent splashes
        
        colors = [PRIMARY_COLOR, SECONDARY_COLOR, MAGENTA_COLOR, YELLOW_COLOR, GREEN_COLOR, ACCENT_COLOR]
        
        # Create color splash effects
        splash_layer = Image.new('RGBA', (self.width, self.height), (255, 255, 255, 0))
        splash_draw = ImageDraw.Draw(splash_layer)
        
        # Add multiple color splashes
        splash_positions = [
            (150, 100, 200), (300, 500, 180), (120, 350, 160),
            (500, 150, 220), (700, 550, 190), (850, 200, 170),
            (200, 600, 140), (600, 80, 150), (400, 400, 130)
        ]
        
        for i, (x, y, size) in enumerate(splash_positions):
            color = colors[i % len(colors)]
            # Convert hex to RGBA with transparency
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            splash_draw.ellipse([x-size, y-size, x+size, y+size], fill=(r, g, b, 100))
            # Add smaller inner splash
            inner_size = size // 2
            splash_draw.ellipse([x-inner_size, y-inner_size, x+inner_size, y+inner_size], 
                              fill=(r, g, b, 150))
        
        # Apply blur for soft splash effect
        splash_layer = splash_layer.filter(ImageFilter.GaussianBlur(radius=15))
        img.paste(splash_layer, (0, 0), splash_layer)

    def _draw_decorative_borders(self, draw):
        """Draws colorful decorative dot borders."""
        colors = [PRIMARY_COLOR, SECONDARY_COLOR, MAGENTA_COLOR, YELLOW_COLOR, GREEN_COLOR, ACCENT_COLOR]
        dot_size = 6
        spacing = 25
        
        # Top border
        for i, x in enumerate(range(spacing, self.width - spacing, spacing)):
            color = colors[i % len(colors)]
            draw.ellipse([x-dot_size, 15-dot_size, x+dot_size, 15+dot_size], fill=color)
        
        # Bottom border
        for i, x in enumerate(range(spacing, self.width - spacing, spacing)):
            color = colors[i % len(colors)]
            draw.ellipse([x-dot_size, self.height-15-dot_size, x+dot_size, self.height-15+dot_size], fill=color)

    def _draw_perforation(self, draw):
        """Draws a zigzag perforation line."""
        x = self.perforation_x
        zigzag_height = 15
        segment_height = 30
        
        for y in range(40, self.height - 40, segment_height):
            # Zigzag pattern
            draw.line([(x, y), (x + zigzag_height, y + segment_height//2)], fill="#CCCCCC", width=2)
            draw.line([(x + zigzag_height, y + segment_height//2), (x, y + segment_height)], fill="#CCCCCC", width=2)

    def _draw_main_content(self, img, draw, data, fonts, logo_img):
        """Draws the main ticket content with festival styling."""
        left_margin = 60
        
        # Logo area (top left)
        if logo_img:
            logo_size = 100
            logo_resized = logo_img.convert("RGBA").resize((logo_size, logo_size), Image.Resampling.LANCZOS)
            # Create colored background for logo
            draw.rectangle([left_margin-10, 50, left_margin+logo_size+10, 150+10], fill=MAGENTA_COLOR)
            img.paste(logo_resized, (left_margin, 50), logo_resized)
        else:
            # Default logo box
            draw.rectangle([left_margin, 50, left_margin+100, 150], fill=MAGENTA_COLOR, outline=WHITE_BG, width=3)
            draw.text((left_margin+50, 100), "YOUR\nLOGO\nHERE", fill=WHITE_BG, anchor='mm', font=fonts['small'], align='center')
        
        # Orange banner for venue/club name
        banner_y = 60
        banner_height = 50
        draw.rectangle([left_margin+130, banner_y, self.perforation_x-60, banner_y+banner_height], fill=SECONDARY_COLOR)
        club_name = str(data.get('venue', 'YOUR CLUB NAME HERE')).upper()
        draw.text((left_margin+140, banner_y+25), club_name, fill=WHITE_BG, anchor='lm', font=fonts['header'])
        
        # Event Title (Large, styled like "Holi Color Festival")
        title_y = 180
        event_name = str(data.get('event_name') or data.get('event_title') or 'COLOR FESTIVAL').upper()
        
        # Split into words for multi-color effect
        words = event_name.split()
        current_y = title_y
        for i, word in enumerate(words):
            color = [PRIMARY_COLOR, SECONDARY_COLOR, MAGENTA_COLOR][i % 3]
            draw.text((left_margin, current_y), word, fill=color, anchor='lm', font=fonts['event_title'])
            current_y += 110
        
        # Date badge (styled circle)
        date_str = str(data.get('event_date', 'DEC 31'))
        date_parts = date_str.split()
        if len(date_parts) >= 2:
            day = date_parts[-1].replace(',', '')  # Get day number
            month = ' '.join(date_parts[:-1]).upper()  # Get month
        else:
            day = "31"
            month = "DEC"
        
        circle_x, circle_y = 750, 250
        circle_radius = 80
        draw.ellipse([circle_x-circle_radius, circle_y-circle_radius, 
                     circle_x+circle_radius, circle_y+circle_radius], 
                    fill=WHITE_BG, outline=PRIMARY_COLOR, width=4)
        draw.text((circle_x, circle_y-25), day, fill=PRIMARY_COLOR, anchor='mm', font=fonts['date_large'])
        draw.text((circle_x, circle_y+35), month, fill=DARK_TEXT, anchor='mm', font=fonts['header'])
        
        # Event details box
        details_y = 420
        time_str = str(data.get('event_time', '6PM - 10PM')).upper()
        venue_str = str(data.get('venue', 'Club Name Here')).upper()
        
        draw.text((left_margin, details_y), time_str, fill=DARK_TEXT, anchor='lm', font=fonts['body'])
        draw.text((left_margin, details_y + 40), venue_str, fill=DARK_TEXT, anchor='lm', font=fonts['body'])
        
        features_text = "COLOR FIGHT • FEATURED DRINKS • LIVE MUSIC • SWEETS"
        draw.text((left_margin, details_y + 110), features_text, fill=DARK_TEXT, anchor='lm', font=fonts['small'])
        
        # Price badge (bottom left)
        price_str = str(data.get('price', '799 INR')).upper()
        price_y = self.height - 120
        draw.text((left_margin, price_y-30), "TICKET PRICE", fill=DARK_TEXT, anchor='lm', font=fonts['small'])
        draw.text((left_margin, price_y+20), price_str, fill=MAGENTA_COLOR, anchor='lm', font=fonts['date_large'])

    def _draw_stub_section(self, img, draw, qr_img, data, fonts):
        """Draws the right-side stub with vertical text and QR code."""
        stub_x = self.perforation_x + 30
        stub_center = stub_x + (self.width - self.perforation_x) // 2 - 30
        
        # Vertical "BOOKING HERE" text
        from PIL import Image as PILImage
        
        # Attendee name vertical
        attendee_name = (
            data.get('name') or 
            data.get('attendee_name') or 
            data.get('holder_name') or 
            'GUEST'
        )
        attendee_name = str(attendee_name).strip().upper()
        
        # Create vertical text
        booking_text = "BOOKING HERE"
        text_img = PILImage.new('RGBA', (400, 100), (255, 255, 255, 0))
        text_draw = ImageDraw.Draw(text_img)
        text_draw.text((10, 50), booking_text, fill=PRIMARY_COLOR, anchor='lm', font=fonts['header'])
        text_img_rotated = text_img.rotate(90, expand=True)
        img.paste(text_img_rotated, (stub_x + 20, 200), text_img_rotated)
        
        # QR Code
        qr_size = 180
        qr_y = 80
        qr_x = stub_center - qr_size // 2
        
        # Orange background for QR
        qr_padding = 15
        draw.rectangle([qr_x-qr_padding, qr_y-qr_padding, 
                       qr_x+qr_size+qr_padding, qr_y+qr_size+qr_padding], 
                      fill=SECONDARY_COLOR)
        
        # White inner background
        draw.rectangle([qr_x-5, qr_y-5, qr_x+qr_size+5, qr_y+qr_size+5], fill=WHITE_BG)
        
        qr_resized = qr_img.convert("RGBA").resize((qr_size, qr_size), Image.Resampling.LANCZOS)
        img.paste(qr_resized, (qr_x, qr_y), qr_resized)
        
        # Ticket info below QR
        info_y = qr_y + qr_size + 40
        
        # Attendee name
        draw.text((stub_center, info_y), "Holi Color", fill=PRIMARY_COLOR, anchor='mm', font=fonts['body'])
        draw.text((stub_center, info_y + 35), "Festival", fill=SECONDARY_COLOR, anchor='mm', font=fonts['body'])
        
        # Sequence number
        seq = str(data.get('sequence_number', '001')).zfill(3)
        draw.text((stub_center, info_y + 100), f"FEST ID: #{seq}", fill=DARK_TEXT, anchor='mm', font=fonts['label'])
        
        # Vertical attendee name at bottom
        attendee_img = PILImage.new('RGBA', (500, 100), (255, 255, 255, 0))
        attendee_draw = ImageDraw.Draw(attendee_img)
        attendee_draw.text((10, 50), attendee_name, fill=DARK_TEXT, anchor='lm', font=fonts['attendee'])
        attendee_img_rotated = attendee_img.rotate(90, expand=True)
        img.paste(attendee_img_rotated, (stub_x + 20, self.height - 280), attendee_img_rotated)
        
        # "ENTRY HERE" arrow at bottom
        entry_y = self.height - 100
        draw.text((stub_center, entry_y), "← ENTRY", fill=SECONDARY_COLOR, anchor='mm', font=fonts['body'])
        draw.text((stub_center, entry_y + 30), "HERE", fill=SECONDARY_COLOR, anchor='mm', font=fonts['body'])

# Initialize instance
pass_designer = PassDesigner()