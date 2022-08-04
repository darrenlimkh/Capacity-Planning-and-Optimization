# Manufacturing Capacity Planning

## Introduction
The development allows for two analyses: quarterly & bluesky capacity planning.

### Quarterly Capacity
The quarterly demand values are declared in 'Capacity Template.xlsx' and based on the operation configurations defined in 'Configurations.xlsx', the relevant P2M values are computed. The following summarises the features of the tab.

1. The datatable rendered onto the frontend allows for sorting by clicking on the column headers. Filters are enabled in the search bar found in the top-right-hand corner of the table. Multiple filters can be done by inputting a space between each filters. P2M values that exceed 0.91 are highlighted in red, while P2M values that are between 0.8 and 0.91 are highlighted in yellow.

2. Global variables/assumptions (i.e., Cycle Time Reduction, Backend Loading, Volume Increment, Available Duration) can be adjusted in the frontend by clicking on the Submit button, and the P2M values will be recomputed. Users can revert to the default assumptions by clicking on the Reset button.

3. Optimization can be accessed by clicking on the Optimize button & and a modal will appear. The modal contains a form for the user to input the maximum achievable P2M value, and the parameters that can be optimized. Users can check one or more of the following variables: SLH, Number Operations, Number Operator/Operations. Boundary values for each variable can be set by the user accordingly. When optimized, rows that reflect changes are highlighted in blue and displayed in parantheses.

4. The results can be exported by clicking on the Export button and an excel file will be downloaded into the browser. The excel file will contain inputs, changelogs, intermediate computations and outputs for all financial year demand data.

5. A seperate tab titled 'MPP' allows for trawling of MPP data from the tableau server. User can input the start & end date, and click on the 'Trawl Tableau MPP Data' to perform the data extraction and processing. Subsequently, user can click on the download icon to attain the required values that can be copied and pasted into an external template.

MPP data is extracted based on:

### Bluesky Capacity
The bluesky demand values are declared in 'Capacity Template.xlsx' and based on the operation configurations defined in 'Configurations.xlsx', the required operations to meet 0.91 P2m are computed. The following summarises the features of the tab.

1. The datatable rendered onto the frontend allows for sorting by clicking on the column headers. Filters are enabled in the search bar found in the top-right-hand corner of the table. Multiple filters can be done by inputting a space between each filters. The operation required in each space group, as well as the year-on-year operation increments and space increments are shown in the datatable. Increments are highlighted in green, while decrements are highlighted in red. There are three tabs namely: Base, Blue and Peak Blue which can be assessed on the top-left-hand corner.

2. Global variables/assumptions (i.e., Cycle Time Reduction, Backend Loading, Volume Increment, Available Duration) can be adjusted in the frontend by clicking on the Submit button, and the operation requirements will be recomputed. Users can revert to the default assumptions by clicking on the Reset button.

4. The results can be exported by clicking on the Export button and an excel file will be downloaded into the browser. The excel file will contain inputs, changelogs, intermediate computations and outputs for all financial year demand data.

### Changelog
The changelog is designed so that scenario studies can be performed without changing the base data/configuration. The changelog can be accessed via the Configurations tab to alter the 'Capacity Template.xlsx' file. There are two changelogs namely, product and operations.

#### Scenario 1: Performing a Scenario Study
Under the 'Scenario Study/Permanent' column, indicate 'Scenario Study' to perform a temporary adjustment to the product/operation values. Changes will not alter the main configuration file, but changes can be observed via the 'Intermediate' sheet of the output. As such, the Intermediate sheet aims to resolve the black-box approach to the analysis

#### Scenario 2: Performing a Permanent Update
Under the 'Scenario Study/Permanent' column, indicate 'Permanent' to perform a fixed adjustment to the product/operation values. Changes will alter the main configuration file, and changes can be observed in both 'Intermediate' and 'Input' sheets of the output.
Permanent changes will see the intial value being updated to 'Permanenet (Updated as of YYYY-MM-DD)'.

#### Scenario 3: Invalid Input
Invalid input such as defining an incorrect product/operation (i.e., don't exist in the configuration file) and/or wrong breakdown type, wrong intial value will cause the mapping to fail. In this case, the errors will be reflected under the 'Errors' column to bring attention to the user to make the necessary adjustments. 

## Getting Started
To run the project locally, the following codes are to be run in the terminal at the project root folder.

1. Activate virtual environment:  ```.venv\Scripts\activate```

2. Run the application file:  ```python app.py```

3. The application is hosted on a local server: ```http://127.0.0.1:5000/```

p.s., creating virtual environment: ```python -m venv .venv```, installing packages: ```py -m pip install -r requirements.txt```
