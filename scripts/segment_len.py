import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import osmnx as ox
import networkx as nx

def download_graph(place: str) -> nx.MultiDiGraph:
    G = ox.graph_from_place(place, network_type="bike", simplify=True)
    G = ox.distance.add_edge_lengths(G)
    return G

def plot_length_colormap_map(G, filename="bike_segment_lengths_map.png"):
    """
    Plot the road network with edge colors representing segment lengths and save as an image.
    """
    
    # Get segment lengths
    lengths = []
    for u, v, k, data in G.edges(keys=True, data=True):
        length = data.get('length', 0)
        lengths.append(length)


    # Logarithmic normalization for better color detail
    lengths_arr = np.array(lengths)
    # Add a small constant to avoid log(0)
    log_lengths = np.log1p(lengths_arr)
    min_log = log_lengths.min()
    max_log = log_lengths.max()
    if max_log > min_log:
        norm_log_lengths = (log_lengths - min_log) / (max_log - min_log)
    else:
        norm_log_lengths = np.zeros_like(log_lengths)

    # Map normalized log-lengths to RGBA colors
    cmap = plt.cm.viridis
    edge_colors = [cmap(val) for val in norm_log_lengths]

    fig, ax = ox.plot_graph(
        G,
        node_size=0,
        edge_color=edge_colors,
        edge_linewidth=1,
        show=False,
        close=False,
        bgcolor='w',
        figsize=(36, 36)
    )
    fig.savefig(filename, dpi=600, bbox_inches='tight')
    plt.close(fig)
    print(f"Map saved as {filename} ")

def stats(G):
    # Extract edge lengths
    lengths = []
    for u, v, k, data in G.edges(keys=True, data=True):
        length = data.get('length')
        if length is not None:
            lengths.append(length)
    lengths = np.array(lengths)
    
    # Create pandas Series for statistics
    lengths_series = pd.Series(lengths)
    print("Granular statistics for segment lengths (meters):")
    print(lengths_series.describe(percentiles=[0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99]))
    print("\nAdditional stats:")
    print(f"Mode: {lengths_series.mode().values}")

if __name__ == "__main__":
  
    G = download_graph("Turin, Italy")

    #stats(G)
    
    # Plot the road network with edge colors representing segment lengths
    plot_length_colormap_map(G, filename="segment_lengths_map.png")
  