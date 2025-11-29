"""Ping tracking and visualization module"""
import time
from collections import deque
from datetime import datetime, timedelta
from typing import List, Tuple
import io
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from utils.logger import setup_logger

logger = setup_logger(__name__)

class PingTracker:
    """Tracks ping values and generates graphs"""

    def __init__(self, max_samples: int = 60):
        """
        Initialize ping tracker

        Args:
            max_samples: Maximum number of ping samples to keep (default: 60)
        """
        self.max_samples = max_samples
        self.pings: deque = deque(maxlen=max_samples)  # (timestamp, latency_ms)

    def add_ping(self, latency_ms: int) -> None:
        """
        Add a ping measurement

        Args:
            latency_ms: Latency in milliseconds
        """
        self.pings.append((datetime.now(), latency_ms))
        logger.debug(f"Added ping: {latency_ms}ms")

    def get_average_ping(self) -> float:
        """Get average ping from all recorded samples"""
        if not self.pings:
            return 0.0
        return sum(p[1] for p in self.pings) / len(self.pings)

    def get_min_ping(self) -> int:
        """Get minimum ping from all recorded samples"""
        if not self.pings:
            return 0
        return min(p[1] for p in self.pings)

    def get_max_ping(self) -> int:
        """Get maximum ping from all recorded samples"""
        if not self.pings:
            return 0
        return max(p[1] for p in self.pings)

    def get_recent_pings(self, minutes: int = 5) -> List[Tuple[datetime, int]]:
        """
        Get pings from the last N minutes

        Args:
            minutes: Number of minutes to look back

        Returns:
            List of (timestamp, latency_ms) tuples
        """
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [p for p in self.pings if p[0] >= cutoff_time]

    def generate_graph(self) -> io.BytesIO:
        """
        Generate a ping graph and return as image bytes

        Returns:
            BytesIO object containing the PNG image
        """
        if not self.pings:
            return self._create_empty_graph()

        try:
            # Get data
            timestamps = [p[0] for p in self.pings]
            latencies = [p[1] for p in self.pings]

            # Create figure and axis
            fig, ax = plt.subplots(figsize=(10, 6), dpi=100)
            fig.patch.set_facecolor('#2C2F33')
            ax.set_facecolor('#23272A')

            # Plot data
            ax.plot(timestamps, latencies, color='#7289DA', linewidth=2, marker='o', markersize=4, label='Ping')
            ax.fill_between(timestamps, latencies, alpha=0.3, color='#7289DA')

            # Calculate stats
            avg_ping = self.get_average_ping()
            min_ping = self.get_min_ping()
            max_ping = self.get_max_ping()

            # Add horizontal line for average
            ax.axhline(y=avg_ping, color='#43B581', linestyle='--', linewidth=2, label=f'Average: {avg_ping:.0f}ms')

            # Format axes
            ax.set_xlabel('Time', color='#FFFFFF', fontsize=10)
            ax.set_ylabel('Latency (ms)', color='#FFFFFF', fontsize=10)
            ax.set_title('Bot Latency Over Time', color='#FFFFFF', fontsize=14, fontweight='bold')

            # Format x-axis
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

            # Style
            ax.tick_params(colors='#FFFFFF')
            ax.spines['bottom'].set_color('#FFFFFF')
            ax.spines['left'].set_color('#FFFFFF')
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.grid(True, alpha=0.2, color='#FFFFFF')
            ax.legend(loc='upper left', facecolor='#2C2F33', edgecolor='#FFFFFF', labelcolor='#FFFFFF')

            # Add stats text
            stats_text = f'Min: {min_ping}ms | Max: {max_ping}ms | Samples: {len(self.pings)}'
            ax.text(0.5, -0.15, stats_text, transform=ax.transAxes, ha='center', color='#FFFFFF', fontsize=9)

            # Save to bytes
            buf = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buf, format='png', facecolor='#2C2F33', edgecolor='none')
            buf.seek(0)
            plt.close(fig)

            return buf

        except Exception as e:
            logger.error(f"Error generating graph: {str(e)}")
            return self._create_empty_graph()

    def _create_empty_graph(self) -> io.BytesIO:
        """Create an empty graph when no data is available"""
        fig, ax = plt.subplots(figsize=(10, 6), dpi=100)
        fig.patch.set_facecolor('#2C2F33')
        ax.set_facecolor('#23272A')

        ax.text(0.5, 0.5, 'No ping data available yet', ha='center', va='center',
                color='#FFFFFF', fontsize=14, transform=ax.transAxes)

        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')

        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor='#2C2F33', edgecolor='none')
        buf.seek(0)
        plt.close(fig)

        return buf

    def clear_data(self) -> None:
        """Clear all ping data"""
        self.pings.clear()
        logger.info("Ping data cleared")


# Global ping tracker instance
ping_tracker = PingTracker(max_samples=60)
