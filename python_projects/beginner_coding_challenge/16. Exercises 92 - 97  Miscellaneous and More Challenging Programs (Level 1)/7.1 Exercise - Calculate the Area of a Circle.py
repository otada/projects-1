import math

diameter = int(input("Please enter the diameter: "))
radius = diameter/2

area = round(math.pi * (radius**2), 2)

print(f"The area of a circle with diameter {diameter} is {area}")