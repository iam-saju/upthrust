#number is a 2digit and 3 digit 
count=0 
num=int(input("enter a number : "))
while num>0:
    count+=1
    num=num//10

print('the number of digits is :',count)


#abs of a number 
num=int(input("enter a number : "))
print(abs(num))


#marks 
mark1=int(input("enter marks of subject 1 : "))
mark2=int(input("enter marks of subject 2 : "))
mark3=int(input("enter marks of subject 3 : "))

if mark1>=35: 
    print("pass") 
else: 
    print("fail")
if mark2>=35: 
    print("pass") 
else: 
    print("fail")
if mark3>=35: 
    print("pass") 
else: 
    print("fail")

#calculator 
num1=int(input("enter first number : "))
num2=int(input("enter second number : "))

print("1. addition")
print("2. subtraction")
print("3. multiplication")
print("4. division")

choice=int(input("enter your choice : "))

if choice==1: print(num1+num2)
elif choice==2: print(num1-num2)
elif choice==3: print(num1*num2)
elif choice==4: print(num1/num2)
else: print("invalid choice")

#ascending numbers 
num1=int(input("enter number1: "))
num2=int(input("enter number 2: "))
num3=int(input("enter number 3: "))
 
if num1<num2 and num1<num3:
    print(num1)
    if num2<num3:
        print(num2)
        print(num3)
    else:
        print(num3)
        print(num2)
elif num2<num1 and num2<num3:
    print(num2)
    if num1<num3:
        print(num1)
        print(num3)
    else:
        print(num3)
        print(num1)
elif num3<num1 and num3<num2:
    print(num3)
    if num1<num2:
        print(num1)
        print(num2)
    else:
        print(num2)
        print(num1)

#descending numbers
num1=int(input("enter number1: "))
num2=int(input("enter number 2: "))
num3=int(input("enter number 3: "))

if num1>num2 and num1>num3:
    print(num1)
    if num2>num3:
        print(num2)
        print(num3)
    else:
        print(num3)
        print(num2)
elif num2>num1 and num2>num3:
    print(num2)
    if num1>num3:
        print(num1)
        print(num3)
    else:
        print(num3)
        print(num1)
elif num3>num1 and num3>num2:
    print(num3)
    if num1>num2:
        print(num1)
        print(num2)
    else:
        print(num2)
        print(num1)

#calculate 5 marks its avg anfd total
mark1=int(input("enter marks of subject 1: "))
mark2=int(input("enter marks of subject 2: "))
mark3=int(input("enter marks of subject 3: "))
mark4=int(input("enter marks of subject 4: "))
mark5=int(input("enter marks of subject 5: "))

total=mark1+mark2+mark3+mark4+mark5
print("total marks: ",total)

average=total/5
print("average marks: ",average)

#armstrong number 
num=int(input("enter a numebr :"))
dup=num
sum=0
while num>0:
    temp=num%10
    sum+=temp**3
    num=num//10
if sum==dup:
    print("armstrong number")
else:
    print("not a armstrong number")

#parking charge 
hrs=int(input("enter hours parked : "))
if hrs>=5:
    print("fare : ",hrs*50)
elif hrs>=3 and hrs<=5:
    print("fare : ",hrs*20)
elif hrs<=2:
    print("fare is free")

#puzzle of a number 
num1=int(input("enter number1: "))
num2=int(input("enter number 2: "))
num3=int(input("enter number 3: "))

if num1>num2 and num1>num3 and num1<num3:
    print("yes")
else:
    print("no")

#movie tocket price
age = int(input("enter age: "))
if age < 12:
    price = 100
elif age <= 59:
    price = 150
else:
    price = 120
print("ticket price :", price)


#2nd largest number 
a = int(input("enter first number: "))
b = int(input("enter second number: "))
c = int(input("enter third number: "))
d = int(input("enter fourth number: "))
l=[a,b,c,d]
max1=-1111
max2=-1111

for i in range(0,4):
    if l[i]>max1:
        max2=max1
        max1=l[i]
    if l[i]>max2 and l[i]<=max1:
        max2=l[i]

print("Second Largest =", max2)



#day of the week 
day = int(input("Enter number (1-7): "))

if day == 1:
    print("Sunday")
elif day == 2:
    print("Monday")
elif day == 3:
    print("Tuesday")
elif day == 4:
    print("Wednesday")
elif day == 5:
    print("Thursday")
elif day == 6:
    print("Friday")
elif day == 7:
    print("Saturday")
else:
    print("Invalid input")

#triangle type
a = int(input("Enter first side: "))
b = int(input("Enter second side: "))
c = int(input("Enter third side: "))

if a == b == c:
    print("Equilateral Triangle")
elif a == b or b == c or a == c:
    print("Isosceles Triangle")
else:
    print("Scalene Triangle")


#greatest and smallest number
a = int(input("Enter 1st number: "))
b = int(input("Enter 2nd number: "))
c = int(input("Enter 3rd number: "))
d = int(input("Enter 4th number: "))

greatest = max(a, b, c, d)
smallest = min(a, b, c, d)

print("greatest =", greatest)
print("smallest =", smallest)


#vehicle speed
speed = int(input("enter vehicle speed: "))

if speed <= 30:
    print("Slow")
elif speed <= 60:
    print("moderate")
elif speed <= 100:
    print("fast")
else:
    print("very Fast")


#odd and ecven month 
month = int(input("enter month number (1-12): "))

if month == 2:
    print("ppecial Month")
elif 1 <= month <= 12:
    if month % 2 == 0:
        print("even")
    else:
        print("Odd")
else:
    print("error")



