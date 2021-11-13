base = int(input("Enter the base: "))
height = int(input("Enter the height: "))

if base > 0 and height > 0:
	area = round((base*height)/2, 2)
	print(f"The area of a triangle with base {base} and height {height} is: {area}")
else:
	print("Please enter valid values for base and height")