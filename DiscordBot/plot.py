import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from library import *


#================================================================================================
# Graph generation
#================================================================================================
# Scatter plot generation
#================================================================================================

def create_scatterplot_from_json(data, lifebar_info, output_file='scatterplot.png'):

    # Set plot size
    fig, ax2 = plt.subplots(figsize=(10, 2))  # Size in inches (1000x200 pixels)
    ax2.axis('off')

    # Create a secondary axis for the density plot
    ax1 = ax2.twinx()

    # Add a horizontal line at y = -100 (center of judgement)
    ax1.axhline(y=-100, color='white', linestyle='-', alpha=0.3, linewidth=2)

    if data is not None:
        # Extract x, y, and color values, excluding points with y=0 or y=200 (misses)
        x_values = [point['x'] for point in data if point['y'] not in [0, 200]]
        y_values = [-point['y'] for point in data if point['y'] not in [0, 200]]
        colors = [point['color'] for point in data if point['y'] not in [0, 200]]
        
        # Create the density plot
        x_dens = [point['x'] for point in data if point['y'] not in [0]]
        density = np.histogram(x_dens, bins=40, density=True)
        x_density = (density[1][1:] + density[1][:-1]) / 2
        y_density = density[0]

        # Plot the density plot
        ax2.plot(x_density, y_density, color='white', alpha=0.0)
        ax2.fill_between(x_density, y_density, color='cyan', alpha=0.2)  
        



        # Add the step scatter points
        ax1.scatter(x_values, y_values, c=colors, marker='s', s=5)
        
        # Add vertical lines for all points with y=200 (misses)
        for point in data:
            if point['y'] == 200:
                vertical_line_color = point['color']
                ax1.axvline(x=point['x'], color=vertical_line_color, linestyle='-')
    

    # Extract lifebarInfo data points
    lifebar_x_values = [point['x'] for point in lifebar_info]
    lifebar_y_values = [-200 + point['y'] for point in lifebar_info]

    # Plot lifebarInfo as a continuous line
    ax1.plot(lifebar_x_values, lifebar_y_values, color='white', linestyle='-', linewidth=2)

    if data is None:
        # Fill under the lifebar curve
        ax1.fill_between(lifebar_x_values, lifebar_y_values, -210, color='cyan', alpha=0.2)


    # Set the x-axis limits to 0 to 1000
    ax1.set_xlim(0, 1000)
    # Set the y-axis limits to -210 to 10
    ax1.set_ylim(-210, 10)
    ax1.axis('off')
    ax1.set_facecolor('black')
    fig.patch.set_facecolor('black')


    # Save the plot as an image
    plt.savefig(output_file, bbox_inches='tight', pad_inches=0)
    plt.close()



#================================================================================================
# Distribution generation
#================================================================================================

def create_distribution_from_json(data, worstWindow,  output_file='distribution.png'):

    # Assuming x_values and y_values are already defined
    y_values = [point['y'] for point in data if point['y'] not in [0, 200]]
    
    jt = set_scale(worstWindow)

    # Create a figure
    plt.figure(figsize=(10, 6))
    kde = sns.kdeplot(y_values, color='black', alpha=0, bw_adjust=0.12)

    # Get the x and y data from the KDE plot
    x_data = kde.get_lines()[0].get_xdata()
    y_data = kde.get_lines()[0].get_ydata()

    # Ensure x_data and y_data are single lists
    if isinstance(x_data[0], np.ndarray):
        x_data = np.concatenate(x_data)
    if isinstance(y_data[0], np.ndarray):
        y_data = np.concatenate(y_data)

    plt.axvline(x=100, color='white', alpha=0.5 , linestyle='-', linewidth=3)
    
    # Fill the area under the curve with different colors
    plt.fill_between(x_data, y_data, where=((x_data >= jt['l_wo']) & (x_data <= jt['e_wo'])), color='#c9855e')
    plt.fill_between(x_data, y_data, where=((x_data >= jt['l_de']) & (x_data <= jt['e_de'])), color='#b45cff')
    plt.fill_between(x_data, y_data, where=((x_data >= jt['l_gr']) & (x_data <= jt['e_gr'])), color='#66c955')
    plt.fill_between(x_data, y_data, where=((x_data >= jt['l_ex']) & (x_data <= jt['e_ex'])), color='#e29c18')
    plt.fill_between(x_data, y_data, where=((x_data >= jt['l_fa']) & (x_data <= jt['e_fa'])), color='#ffffff')
    plt.fill_between(x_data, y_data, where=((x_data >= jt['l_fap']) & (x_data <= jt['e_fap'])), color='#21cce8')

    # Set the x-axis
    plt.xlim(0, 200)
    # Adjust the y-axis limits to place the peak at around 3/4 of the height
    max_density = max(y_data)
    plt.ylim(0, max_density * 1.33)

    # Flip the x-axis
    plt.gca().invert_xaxis()

    plt.axis('off')
    plt.gca().set_facecolor('black')
    plt.gcf().patch.set_facecolor('black')
    plt.savefig(output_file, bbox_inches='tight', pad_inches=0)
    plt.close()