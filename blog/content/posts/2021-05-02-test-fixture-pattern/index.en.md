---
title: "Share context between tests with fixtures"
date: 2021-05-02T00:00:00+02:00
draft: false
author: "Marcel"
description: "Imagine your about to sit down to eat your lunch. The dirty breakfast dish is still on the table. You got three options. You can get a new plate, you can clean the old plate, or you can just eat lunch off the dirty plate. Thats it. New plate, clean plate, dirty plate. The same rules apply to tests."
images: []
resources:
- name: "featured-image"
  src: "featured-image.jpg"

tags: ["UnitTest", "C-Sharp", ".Net"]

lightgallery: true
---

## Test Fixtures

Imagine your about to sit down to eat your lunch. The dirty breakfast dish is still on the table. You got three options. You can get a new plate, you can clean the old plate, or you can just eat lunch off the dirty plate. Thats it. New plate, clean plate, dirty plate. The same rules apply to tests.

### Transient Fresh Fixture

Getting a new plate is what Meszaros calls in the book "XUnit Test Patterns" a Transient Fresh Fixture. The fixture is created from scratch at the beginning of each test.

Let say, we have the following Test class.

```csharp
public class FreshFixtureTests
{
    [Fact]
    public void TestOne()
    {
        Debug.WriteLine("Execute Test 1");
        var stack = new Stack<int>();

        var count = stack.Count;
        Assert.Equal(0, count);
    }

    [Fact]
    public void TestTwo()
    {
        Debug.WriteLine("Execute Test 2");
        var stack = new Stack<int>();

        stack.Push(42);

        var count = stack.Count;
        Assert.Equal(1, count);
    }
}
```

Both tests share the same common arrangement.

```csharp
var stack = new Stack<int>();
```

A transient fresh fixture is easy to show in Xunit, because this is the kind of fixture that Xunit encourages. You can share the common code with the constructor of the test class.

```csharp
public class FreshFixtureTests
{
    Stack<int> stack;

    public FreshFixtureTests()
    {
        Debug.WriteLine("Initialize Fixture");
        stack = new Stack<int>();
    }

    //...
}
```

Now, when we execute these tests, look what happens.

```
Initialize Fixture
Execute Test 1
Initialize Fixture
Execute Test 2
```

We see that the constructor for the FreshFixtureTests gets executed prior to each of the test methods. This means that each test method is being executed on an entirely new instance of the test class.

This is a classic transient fresh fixture. It is transient because it’s lifetime is restricted to the duration of a single test. It is fresh because it is newly initialized prior to each test. This means that the tests cannot communicate with each other, and can therefore be run in any order.

But what happen if some part of your test fixture isn't transient. This means there was something persistent in the test fixture that we needed to reset after the test.

### Persistent Fresh Fixture

Meszaros calls this kind of test fixture Persistent-Fresh. This is the breakfast plate that we clean before eating lunch.

Let’s look in the code.

```csharp

public class FreshFixtureTests : IDisposable
{
    //...

    public void Dispose()
    {
        Debug.WriteLine("Dispose Fixture");
        stack = null;
    }

    //...
}
```

As you can see, when we run it, the dispose function is called after each test.

```
Initialize Fixture
Execute Test 1
Dispose Fixture
Initialize Fixture
Execute Test 2
Dispose Fixture
```

If you can choose, the transient fresh test fixtures are the best approach.

> You should be aware that NUnit for example does not create a new instance of the test class for each test, so your test fixtures are persistent, and you should take care to include appropriate teardown functions.

### Persistent Shared Fixture

The last fixture is the persistent shared fixture. For example if you dispose after each test the database connections, your tests are gonna run forever. Database connections can be pretty expensive. It would probably be better to share a single database connection over the whole suite of tests.

In xunit we use a fixture class with `IClassFixture`.

```csharp
public class DatabaseFixture : IDisposable
{
    public DatabaseFixture()
    {
        Debug.WriteLine("Initialize Shared Fixture");
        // ... initialize data in the test database ...
    }

    public void Dispose()
    {
        Debug.WriteLine("Dispose Shared Fixture");
        // ... clean up test data from the database ...
    }
}
```

```csharp
public class DatabaseTests : IClassFixture<DatabaseFixture>
{
    DatabaseFixture fixture;

    public DatabaseTests(DatabaseFixture fixture)
    {
        this.fixture = fixture;
    }

    [Fact]
    public void Test1()
    {
        Debug.WriteLine("Execute Test 1");
    }

    [Fact]
    public void Test2()
    {
        Debug.WriteLine("Execute Test 2");
    }
}
```

When we run this test we can see that the DatabaseFixture constructor is called add the beginning and dispose after the last test.

```
Initialize Shared Fixture
Execute Test 2
Execute Test 1
Dispose Shared Fixture
```

If you combine all type of fixtures the output would be.

```
Initialize Shared Fixture
Initialize Fixture
Execute Test 1
Dispose Fixture
Initialize Fixture
Execute Test 2
Dispose Fixture
Dispose Shared Fixture
```

Just remember the fresher the better, and transient is top.

You can learn more about this topic [here](http://xunitpatterns.com/Fresh%20Fixture.html) and [here](https://xunit.net/docs/shared-context).