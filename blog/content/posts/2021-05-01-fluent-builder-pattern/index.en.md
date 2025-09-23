---
title: "Create Test Data cleanly with Fluent Builder Pattern"
date: 2021-05-01T00:00:00+02:00
lastmod: 2021-05-01T00:00:00+02:00
draft: false
author: "Marcel"
description: "Helper methods make it easier to create test data. But they can become difficult to read over time as
you need more variations of the test data to satisfy constantly evolving requirements from new tests."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"

tags: ["UnitTest", "C-Sharp", ".Net"]

lightgallery: true
---

Helper methods make it easier to create test data. But they can become difficult to read over time as
you need more variations of the test data to satisfy constantly evolving requirements from new tests.

Let say, we have the following Customer class.

```csharp
public class Customer
{
    public string Name { get; set; }
    public DateTime? DateOfBirth { get; set; }
    public string Email { get; set; }
    public string Address { get; set; }
}
```

In generally we create an instance of the Customer and set the respective properties as shown below.

```csharp
var customer = new Customer();
customer.Name = "Jacob Knight";
customer.DateOfBirth = new DateTime(1988, 5, 1);
customer.Email = "nofec547@anim.com";
customer.Address = "4429 Kelley Road";
```

The second step could be a helper method.
This helper method starts with just a single parameter:

```csharp
var customer = NewCustomer("Jacob Knight");
```

But soon it acquires more and more parameters. Conditionals creep into the NewCustomer() method body to handle the nulls,
and the method calls become hard to read due to the long parameter lists:

```csharp
var validDate = NewCustomer("", new DateTime(1988, 5, 1), null, null);
var validEmail = NewCustomer(null, null, "nofec547@anim.com", null);
var validAddress = NewCustomer(null, null, null, "4429 Kelley Road");
```

Or a new method is added each time a test needs a different combination of fields:

```csharp
var validDate = NewCustomerWithDate("Jacob Knight", new DateTime(1988, 5, 1));
var validEmail = NewCustomerWithEmail("nofec547@anim.com");
var validAddress = NewCustomerWithAddress("4429 Kelley Road");
```

Instead you can use the fluent builder pattern: create a helper method that returns a partially-built object whose state can be overridden in tests. The helper method initializes logically-required fields to reasonable defaults, so each test can specify only
fields relevant to the case being tested:

```csharp
public class CustomerBuilder
{
    private string _name;
    private DateTime? _dateOfBirth;
    private string _email;
    private string _address;

    public CustomerBuilder WithName(string name)
    {
        _name = name;
        return this;
    }

    public CustomerBuilder WithDateOfBirth(DateTime? dateOfBirth)
    {
        _dateOfBirth = dateOfBirth;
        return this;
    }

    public CustomerBuilder WithEmail(string email)
    {
        _email = email;
        return this;
    }

    public CustomerBuilder WithAddress(string address)
    {
        _address = address;
        return this;
    }

    public Customer Build()
    {
        return new Customer()
        {
            Name = _name,
            DateOfBirth = _dateOfBirth,
            Email = _email,
            Address = _address
        };
    }
}
```

You can use it now like:

```csharp
var customer = new CustomerBuilder()
            .WithName("Jacob Knight")
            .WithDateOfBirth(Convert.ToDateTime("01/05/1988"))
            .WithEmail("nofec547@anim.com")
            .WithAddress("4429 Kelley Roa")
            .Build();
```

With an implicit operator in the CustomerBuilder you can also hide the Build() part.

```csharp
public class CustomerBuilder
{
    //...

    public static implicit operator Customer(CustomerBuilder instance)
    {
        return instance.Build();
    }
}
```

```csharp
Customer implicitCustomer = new CustomerBuilder()
            .WithName("Jacob Knight")
            .WithDateOfBirth(Convert.ToDateTime("01/05/1988"))
            .WithEmail("nofec547@anim.com")
            .WithAddress("4429 Kelley Roa");
```

A big benefit is that the test code is now easier to write and read because the parameters are clearly identified.

Also note that tests should never rely on default values that are specified by a helper method since
that forces readers to read the helper method’s implementation details in order to understand the test.

In some cases, Builders have so improved the code that they ended up being used in the production code as well.

You can learn more about this topic [here](http://www.natpryce.com/articles/000714.html).